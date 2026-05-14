import json
import logging
import signal
import time
import uuid
from pathlib import Path

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from core.config import settings
from core.event_manager import EventManager
from core.task_manager import TASK_TYPE_PERSON, TASK_TYPE_PREPROCESSING, TaskManager
from db.models import Task, TaskStatus, Video
from db.session import SessionLocal, init_db

logger = logging.getLogger("video_analysis.person_worker")
LOCK_TTL_SECONDS = 3600
SHUTDOWN_REQUESTED = False
_VISION_PIPELINE = None


def _request_shutdown(_signum: int, _frame: object) -> None:
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True


def get_vision_pipeline():
    global _VISION_PIPELINE
    if _VISION_PIPELINE is None:
        from models.pipeline import VisionPipeline

        _VISION_PIPELINE = VisionPipeline()
    return _VISION_PIPELINE


def preprocessing_state(db, video_id: str) -> str:
    """Return one of: 'success', 'failed', 'in_progress', 'missing'."""
    preprocessing = db.execute(
        select(Task).where(Task.video_id == video_id, Task.type == TASK_TYPE_PREPROCESSING).limit(1)
    ).scalar_one_or_none()
    if preprocessing is None:
        return "missing"
    if preprocessing.status == TaskStatus.success:
        return "success"
    if preprocessing.status == TaskStatus.failed:
        return "failed"
    return "in_progress"


def process_person_task(task_id: str) -> None:
    db = SessionLocal()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    task_manager = TaskManager(db=db, redis_client=redis_client)
    event_manager = EventManager(db=db)
    lock_key = f"task:lock:{task_id}"
    lock_value = str(uuid.uuid4())

    try:
        task = None
        for _ in range(10):
            task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
            if task is not None:
                break
            time.sleep(0.2)
        if task is None:
            logger.warning("task_missing_after_retry", extra={"task_id": task_id, "worker": "person"})
            return
        if task.type != TASK_TYPE_PERSON:
            raise RuntimeError(f"Unsupported task type: {task.type}")

        execution_hash = str(task.payload.get("execution_hash", ""))
        if execution_hash:
            lock_key = f"task:execution_lock:{execution_hash}"
        lock_acquired = redis_client.set(lock_key, lock_value, nx=True, ex=LOCK_TTL_SECONDS)
        if not lock_acquired:
            return

        if task.status == TaskStatus.success:
            return

        video = db.execute(select(Video).where(Video.id == task.video_id)).scalar_one_or_none()
        if video is None:
            raise RuntimeError(f"Video not found for task {task_id}")

        state = preprocessing_state(db, task.video_id)
        if state == "failed":
            # Don't infinitely re-queue. Mark this person task failed so the
            # video reaches a terminal state and clients stop polling.
            task_manager.mark_task_failed(task, "preprocessing failed; person task cannot run")
            task_manager.sync_video_status_from_task(video, task)
            db.commit()
            return
        if state in ("in_progress", "missing"):
            time.sleep(0.5)
            redis_client.lpush(
                settings.person_queue_name,
                json.dumps({"task_id": task.id, "video_id": task.video_id, "task_type": task.type}),
            )
            return

        frames_dir = Path(task.payload.get("frames_dir", ""))
        if not frames_dir.exists():
            raise RuntimeError(f"Frames directory not found: {frames_dir}")
        frame_files = sorted(frames_dir.glob("frame_*.jpg"))
        if not frame_files:
            raise RuntimeError(f"No frames found for person detection: {frames_dir}")

        fps = float(task.payload.get("config_snapshot", {}).get("frame_sampling_fps", settings.frame_sampling_fps))

        task_manager.mark_task_running(task)
        task_manager.sync_video_status_from_task(video, task)
        db.commit()

        pipeline = get_vision_pipeline()
        analysis = pipeline.analyze_frames(frame_files, fps)

        person_tracks = []
        events = []
        for track in analysis.tracks:
            if not track.observations:
                continue
            detections = [
                {
                    "timestamp_sec": obs.timestamp_sec,
                    "bbox": obs.bbox,
                    "confidence": obs.confidence,
                    "frame_width": obs.frame_width,
                    "frame_height": obs.frame_height,
                    "face_bbox": obs.face_bbox,
                }
                for obs in track.observations
            ]
            person_tracks.append(
                {
                    "track_id": track.track_id,
                    "start_sec": track.start_sec,
                    "end_sec": track.last_sec,
                    "confidence": track.best_conf,
                    "boxes": detections,
                }
            )
            first_bbox = detections[0]["bbox"]
            last_bbox = detections[-1]["bbox"]
            events.append(
                {
                    "event_id": f"{task.id}:{track.track_id}:start",
                    "job_id": task.video_id,
                    "event_type": "person_track_start",
                    "timestamp_sec": track.start_sec,
                    "confidence": track.best_conf,
                    "source": "person_worker",
                    "payload": {"track_id": track.track_id, "bbox": first_bbox},
                }
            )
            for det_idx, det in enumerate(detections):
                events.append(
                    {
                        "event_id": f"{task.id}:{track.track_id}:det:{det_idx}",
                        "job_id": task.video_id,
                        "event_type": "person_detected",
                        "timestamp_sec": float(det["timestamp_sec"]),
                        "confidence": float(det["confidence"]),
                        "source": "person.yolo",
                        "payload": {
                            "track_id": track.track_id,
                            "bbox": det["bbox"],
                            "frame_width": det.get("frame_width", 0),
                            "frame_height": det.get("frame_height", 0),
                        },
                    }
                )
            events.append(
                {
                    "event_id": f"{task.id}:{track.track_id}:end",
                    "job_id": task.video_id,
                    "event_type": "person_track_end",
                    "timestamp_sec": track.last_sec,
                    "confidence": track.best_conf,
                    "source": "person_worker",
                    "payload": {"track_id": track.track_id, "bbox": last_bbox},
                }
            )

            action_prediction = analysis.action_by_track.get(track.track_id)
            if action_prediction is not None:
                events.append(
                    {
                        "event_id": f"{task.id}:{track.track_id}:action",
                        "job_id": task.video_id,
                        "event_type": "action_detected",
                        "timestamp_sec": track.last_sec,
                        "confidence": action_prediction.confidence,
                        "source": action_prediction.source,
                        "payload": {
                            "track_id": track.track_id,
                            "action": action_prediction.label,
                        },
                    }
                )

            face_obs = next((obs for obs in track.observations if obs.face_bbox), None)
            if face_obs is not None:
                events.append(
                    {
                        "event_id": f"{task.id}:{track.track_id}:face",
                        "job_id": task.video_id,
                        "event_type": "face_detected",
                        "timestamp_sec": face_obs.timestamp_sec,
                        "confidence": float(face_obs.face_confidence or track.best_conf),
                        "source": "face.insightface",
                        "payload": {
                            "track_id": track.track_id,
                            "identity": "unknown",
                            "bbox": face_obs.face_bbox,
                            "frame_width": face_obs.frame_width,
                            "frame_height": face_obs.frame_height,
                            "embedding": face_obs.face_embedding,
                        },
                    }
                )

        for obj_idx, obj in enumerate(analysis.object_events[:200]):
            events.append(
                {
                    "event_id": f"{task.id}:object:{obj_idx}",
                    "job_id": task.video_id,
                    "event_type": "object_detected",
                    "timestamp_sec": float(obj["timestamp_sec"]),
                    "confidence": float(obj["confidence"]),
                    "source": "object.yolo",
                    "payload": {
                        "label": obj["label"],
                        "bbox": obj["bbox"],
                        "frame_width": obj.get("frame_width", 0),
                        "frame_height": obj.get("frame_height", 0),
                    },
                }
            )
        if events:
            event_manager.commit_event_batch(task.video_id, events)

        task_result = {
            "track_count": len(person_tracks),
            "tracks": person_tracks,
        }
        task_manager.mark_task_success(task, task_result)
        task_manager.sync_video_status_from_task(video, task)
        db.commit()
    except Exception as exc:
        task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
        if task is not None:
            task_manager.mark_task_failed(task, str(exc))
            db.commit()
    finally:
        release_script = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""
        try:
            redis_client.eval(release_script, 1, lock_key, lock_value)
        except Exception:
            logger.exception("task_lock_release_failed")
        db.close()


def run_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    init_db()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    db = SessionLocal()
    event_manager = EventManager(db=db)
    try:
        while not SHUTDOWN_REQUESTED:
            try:
                message = redis_client.brpop(settings.person_queue_name, timeout=5)
            except RedisConnectionError:
                logger.info("redis_unavailable_retrying", extra={"worker": "person"})
                time.sleep(1.0)
                continue
            if not message:
                continue
            _, payload = message
            body = json.loads(payload)
            if body.get("task_type") != TASK_TYPE_PERSON:
                continue
            process_person_task(body["task_id"])
    finally:
        try:
            event_manager.flush_all_buffers()
            db.commit()
        except Exception:
            db.rollback()
        db.close()


if __name__ == "__main__":
    run_worker()
