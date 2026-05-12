import json
import logging
import signal
import shutil
import subprocess
import time
import uuid
import wave
from pathlib import Path

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from core.config import settings
from core.event_manager import EventManager
from core.task_manager import TASK_TYPE_PREPROCESSING, TaskManager
from db.models import Task, TaskStatus, Video
from db.session import SessionLocal, init_db

logger = logging.getLogger("video_analysis.preprocessing_worker")
LOCK_TTL_SECONDS = 3600
SHUTDOWN_REQUESTED = False
_FFMPEG_BINARY: str | None = None


def _request_shutdown(_signum: int, _frame: object) -> None:
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True


def get_ffmpeg_binary() -> str:
    global _FFMPEG_BINARY
    if _FFMPEG_BINARY:
        return _FFMPEG_BINARY
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        _FFMPEG_BINARY = system_ffmpeg
        return _FFMPEG_BINARY
    try:
        import imageio_ffmpeg

        _FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
        return _FFMPEG_BINARY
    except Exception as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("ffmpeg binary is unavailable. Install ffmpeg or imageio-ffmpeg.") from exc


def run_command(command: list[str], task_id: str, video_id: str) -> None:
    resolved = list(command)
    resolved[0] = get_ffmpeg_binary()
    completed = subprocess.run(resolved, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        logger.error(
            "ffmpeg_command_failed",
            extra={
                "task_id": task_id,
                "job_id": video_id,
                "worker": "preprocessing",
                "return_code": completed.returncode,
                "stderr": stderr,
            },
        )
        error = stderr or stdout or "Unknown command error"
        raise RuntimeError(error)


def probe_audio_duration(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as wav_file:
        frame_count = wav_file.getnframes()
        sample_rate = wav_file.getframerate()
        if sample_rate <= 0:
            raise RuntimeError(f"Invalid wav sample rate: {sample_rate}")
        return frame_count / float(sample_rate)


def cleanup_partial_outputs(video_id: str) -> None:
    audio_file = settings.audio_root_path / video_id / "audio.wav"
    frames_dir = settings.frames_root_path / video_id
    if audio_file.exists():
        audio_file.unlink()
    if frames_dir.exists():
        for frame_file in frames_dir.glob("frame_*.jpg"):
            frame_file.unlink()


def process_preprocessing_task(task_id: str) -> None:
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
            logger.warning(
                "task_missing_after_retry",
                extra={"task_id": task_id, "job_id": None, "worker": "preprocessing", "status": "skipped"},
            )
            return
        if task.type != TASK_TYPE_PREPROCESSING:
            raise RuntimeError(f"Unsupported task type: {task.type}")
        execution_hash = str(task.payload.get("execution_hash", ""))
        if execution_hash:
            lock_key = f"task:execution_lock:{execution_hash}"
        lock_acquired = redis_client.set(lock_key, lock_value, nx=True, ex=LOCK_TTL_SECONDS)
        if not lock_acquired:
            logger.info(
                "task_lock_not_acquired",
                extra={
                    "task_id": task_id,
                    "job_id": task.video_id,
                    "worker": "preprocessing",
                    "status": "skipped",
                },
            )
            return
        if task.status == TaskStatus.success:
            logger.info(
                "task_status_change",
                extra={"task_id": task.id, "job_id": task.video_id, "worker": "preprocessing", "status": "skipped"},
            )
            return

        video = db.execute(select(Video).where(Video.id == task.video_id)).scalar_one_or_none()
        if video is None:
            raise RuntimeError(f"Video not found for task {task_id}")

        if execution_hash:
            prior_success_tasks = db.execute(
                select(Task).where(
                    Task.video_id == task.video_id,
                    Task.type == task.type,
                    Task.status == TaskStatus.success,
                )
            ).scalars()
            for prior_task in prior_success_tasks:
                if prior_task.id == task.id:
                    continue
                prior_hash = str(prior_task.payload.get("execution_hash", ""))
                prior_result = prior_task.result or {}
                if prior_hash == execution_hash and prior_result:
                    task_manager.mark_task_success(task, result=prior_result)
                    task_manager.sync_video_status_from_task(video, task)
                    task_manager.mark_video_status(video, video.status, metadata_json=prior_result)
                    db.commit()
                    logger.info(
                        "task_status_change",
                        extra={
                            "task_id": task.id,
                            "job_id": video.id,
                            "worker": "preprocessing",
                            "status": "skipped_idempotent_reuse",
                        },
                    )
                    return

        task_manager.mark_task_running(task)
        task_manager.sync_video_status_from_task(video, task)
        db.commit()
        logger.info(
            "task_status_change",
            extra={"task_id": task.id, "job_id": video.id, "worker": "preprocessing", "status": task.status.value},
        )

        video_id = task.payload["video_id"]
        video_path = Path(task.payload["video_path"])
        if not video_path.exists():
            raise RuntimeError(f"Video file not found: {video_path}")
        frame_sampling_fps = int(task.payload.get("frame_sampling_fps", settings.frame_sampling_fps))
        frame_max_frames = int(task.payload.get("frame_max_frames", settings.frame_max_frames))

        audio_dir = settings.audio_root_path / video_id
        frames_dir = settings.frames_root_path / video_id
        audio_dir.mkdir(parents=True, exist_ok=True)
        frames_dir.mkdir(parents=True, exist_ok=True)
        for frame_file in frames_dir.glob("frame_*.jpg"):
            frame_file.unlink()

        audio_path = audio_dir / "audio.wav"
        run_command(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(audio_path),
            ],
            task_id=task.id,
            video_id=video_id,
        )
        frame_pattern = frames_dir / "frame_%04d.jpg"
        run_command(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"fps={frame_sampling_fps}",
                "-frames:v",
                str(frame_max_frames),
                str(frame_pattern),
            ],
            task_id=task.id,
            video_id=video_id,
        )

        frame_count = len(list(frames_dir.glob("frame_*.jpg")))
        if frame_count == 0:
            raise RuntimeError("No frames were extracted from the video")
        audio_duration = probe_audio_duration(audio_path)

        result = {
            "video_id": video_id,
            "audio_path": str(audio_path),
            "frames_dir": str(frames_dir),
            "frame_count": frame_count,
            "audio_duration_sec": audio_duration,
            "frame_sampling_fps": frame_sampling_fps,
            "frame_max_frames": frame_max_frames,
        }
        event_manager.commit_event_batch(
            video_id,
            [
                {
                    "event_id": f"{task.id}:audio_extracted",
                    "job_id": video_id,
                    "event_type": "audio_extracted",
                    "timestamp_sec": 0.0,
                    "confidence": 1.0,
                    "source": "preprocessing_worker",
                    "payload": {
                        "task_id": task.id,
                        "audio_path": str(audio_path),
                    },
                },
                {
                    "event_id": f"{task.id}:frame_processed",
                    "job_id": video_id,
                    "event_type": "frame_processed",
                    "timestamp_sec": 0.0,
                    "confidence": 1.0,
                    "source": "preprocessing_worker",
                    "payload": {
                        "task_id": task.id,
                        "frames_dir": str(frames_dir),
                        "frame_count": frame_count,
                        "frame_sampling_fps": frame_sampling_fps,
                    },
                },
            ],
        )

        task_manager.mark_task_success(task, result=result)
        audio_task = task_manager.create_audio_task(video=video, audio_path=str(audio_path))
        task_manager.enqueue_task(audio_task)
        task_manager.sync_video_status_from_task(video, audio_task)
        task_manager.mark_video_status(video, video.status, metadata_json=result)
        db.commit()
        logger.info(
            "task_status_change",
            extra={"task_id": task.id, "job_id": video.id, "worker": "preprocessing", "status": task.status.value},
        )
    except Exception as exc:
        task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
        if task is not None:
            video_id = str(task.payload.get("video_id", ""))
            if video_id:
                cleanup_partial_outputs(video_id)
            video = db.execute(select(Video).where(Video.id == task.video_id)).scalar_one_or_none()
            task_manager.mark_task_failed(task, str(exc))
            if video is not None:
                task_manager.sync_video_status_from_task(video, task)
            db.commit()
            logger.error(
                "task_status_change",
                extra={
                    "task_id": task.id,
                    "job_id": task.video_id,
                    "worker": "preprocessing",
                    "status": task.status.value,
                    "error": str(exc),
                },
            )
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
            logger.exception(
                "task_lock_release_failed",
                extra={"task_id": task_id, "job_id": None, "worker": "preprocessing", "status": "warning"},
            )
        db.close()


def run_worker() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    init_db()
    settings.audio_root_path.mkdir(parents=True, exist_ok=True)
    settings.frames_root_path.mkdir(parents=True, exist_ok=True)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    db = SessionLocal()
    event_manager = EventManager(db=db)

    try:
        while not SHUTDOWN_REQUESTED:
            try:
                message = redis_client.brpop(settings.preprocessing_queue_name, timeout=5)
            except RedisConnectionError:
                logger.info("redis_unavailable_retrying", extra={"worker": "preprocessing"})
                time.sleep(1.0)
                continue
            if not message:
                continue
            _, payload = message
            body = json.loads(payload)
            if body.get("task_type") != TASK_TYPE_PREPROCESSING:
                continue
            task_id = body["task_id"]
            process_preprocessing_task(task_id)
    finally:
        try:
            event_manager.flush_all_buffers()
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "event_flush_on_shutdown_failed",
                extra={"task_id": None, "job_id": None, "worker": "preprocessing", "status": "warning"},
            )
        db.close()


if __name__ == "__main__":
    run_worker()
