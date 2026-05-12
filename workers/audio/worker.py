import json
import logging
import math
import os
import re
import signal
import shutil
import time
import uuid
from pathlib import Path

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from core.config import settings
from core.event_manager import EventManager
from core.task_manager import TASK_TYPE_AUDIO, TaskManager
from db.models import Task, TaskStatus, Video
from db.session import SessionLocal, init_db

logger = logging.getLogger("video_analysis.audio_worker")
LOCK_TTL_SECONDS = 3600
SHUTDOWN_REQUESTED = False
_WHISPER_MODEL = None
try:
    import whisper
except Exception:  # pragma: no cover - runtime dependency guard
    whisper = None


def _request_shutdown(_signum: int, _frame: object) -> None:
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True


def ensure_ffmpeg_available_for_whisper() -> None:
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg

        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("ffmpeg is unavailable. Install ffmpeg or imageio-ffmpeg.") from exc
    ffmpeg_path = Path(ffmpeg_bin)
    ffmpeg_dir = ffmpeg_path.parent
    shim_dir = Path.home() / ".local" / "bin"
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim_path = shim_dir / "ffmpeg"
    if not shim_path.exists():
        try:
            shim_path.symlink_to(ffmpeg_path)
        except FileExistsError:
            pass
    if not shim_path.exists():
        raise RuntimeError(f"Unable to create ffmpeg shim at {shim_path}")
    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(":") if current_path else []
    for candidate in (str(shim_dir), str(ffmpeg_dir)):
        if candidate not in path_parts:
            current_path = f"{candidate}:{current_path}" if current_path else candidate
    os.environ["PATH"] = current_path


def get_whisper_model():
    global _WHISPER_MODEL
    ensure_ffmpeg_available_for_whisper()
    if whisper is None:
        raise RuntimeError("Whisper dependency is not installed. Install openai-whisper and torch.")
    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = whisper.load_model(settings.whisper_model_name)
    return _WHISPER_MODEL


def _segment_confidence(segment: dict) -> float:
    avg_logprob = segment.get("avg_logprob")
    if avg_logprob is None:
        return 1.0
    return max(0.0, min(1.0, 1 / (1 + math.exp(-float(avg_logprob)))))


def _is_low_quality_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if not normalized:
        return True
    tokens = [token for token in re.split(r"\W+", normalized) if token]
    if len(tokens) < 2:
        return True
    unique_ratio = len(set(tokens)) / len(tokens)
    return unique_ratio < 0.35


def process_audio_task(task_id: str) -> None:
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
            logger.warning("task_missing_after_retry", extra={"task_id": task_id, "worker": "audio"})
            return
        if task.type != TASK_TYPE_AUDIO:
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

        audio_path = Path(task.payload.get("audio_path", ""))
        if not audio_path.exists():
            raise RuntimeError(f"Audio file not found: {audio_path}")

        task_manager.mark_task_running(task)
        task_manager.sync_video_status_from_task(video, task)
        db.commit()

        model = get_whisper_model()
        language_hint = str(getattr(settings, "whisper_language_hint", "hy") or "hy").strip() or "hy"
        initial_prompt = None
        if language_hint == "hy":
            initial_prompt = getattr(settings, "whisper_initial_prompt_hy", None)

        transcription = model.transcribe(
            str(audio_path),
            task="transcribe",
            language=language_hint,
            initial_prompt=initial_prompt,
            temperature=0,
            fp16=False,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.2,
            verbose=False,
        )
        language_detected = transcription.get("language", language_hint or "unknown")
        raw_segments = transcription.get("segments", [])

        segments = []
        events = []
        for idx, segment in enumerate(raw_segments):
            start_sec = float(segment.get("start", 0.0))
            end_sec = float(segment.get("end", start_sec))
            text = str(segment.get("text", "")).strip()
            confidence = _segment_confidence(segment)
            low_quality = _is_low_quality_text(text)
            if low_quality:
                text = "[Unclear speech/noise - transcription suppressed]"
                confidence = min(confidence, 0.2)
            segment_payload = {
                "start_sec": start_sec,
                "end_sec": end_sec,
                "text": text,
                "confidence": confidence,
                "language_detected": language_detected,
                "transcript_quality": "low" if low_quality else "ok",
            }
            segments.append(segment_payload)
            events.append(
                {
                    "event_id": f"{task.id}:speech_segment:{idx}",
                    "job_id": task.video_id,
                    "event_type": "speech_segment",
                    "timestamp_sec": start_sec,
                    "confidence": confidence,
                    "source": "audio_worker",
                    "payload": segment_payload,
                }
            )

        if events:
            event_manager.commit_event_batch(task.video_id, events)

        task_result = {
            "audio_path": str(audio_path),
            "language_detected": language_detected,
            "segment_count": len(segments),
            "segments": segments,
        }
        task_manager.mark_task_success(task, task_result)
        task_manager.sync_video_status_from_task(video, task)
        db.commit()
    except Exception as exc:
        task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
        if task is not None:
            video = db.execute(select(Video).where(Video.id == task.video_id)).scalar_one_or_none()
            task_manager.mark_task_failed(task, str(exc))
            if video is not None:
                task_manager.sync_video_status_from_task(video, task)
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
                message = redis_client.brpop(settings.audio_queue_name, timeout=5)
            except RedisConnectionError:
                logger.info("redis_unavailable_retrying", extra={"worker": "audio"})
                time.sleep(1.0)
                continue
            if not message:
                continue
            _, payload = message
            body = json.loads(payload)
            if body.get("task_type") != TASK_TYPE_AUDIO:
                continue
            process_audio_task(body["task_id"])
    finally:
        try:
            event_manager.flush_all_buffers()
            db.commit()
        except Exception:
            db.rollback()
        db.close()


if __name__ == "__main__":
    run_worker()
