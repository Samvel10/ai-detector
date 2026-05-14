import json
import hashlib
import logging
from datetime import datetime

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from db.models import Task, TaskStatus, Video, VideoStatus

TASK_TYPE_PREPROCESSING = "preprocessing"
TASK_TYPE_AUDIO = "audio"
TASK_TYPE_PERSON = "person"
logger = logging.getLogger("video_analysis.task_manager")


class TaskManager:
    def __init__(self, db: Session, redis_client: Redis) -> None:
        self.db = db
        self.redis = redis_client

    @staticmethod
    def build_execution_hash(job_id: str, task_type: str, config_snapshot: dict) -> str:
        canonical_snapshot = json.dumps(config_snapshot, sort_keys=True, separators=(",", ":"))
        seed = f"{job_id}:{task_type}:{canonical_snapshot}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def create_preprocessing_task(self, video: Video) -> Task:
        config_snapshot = {
            "frame_sampling_fps": settings.frame_sampling_fps,
            "frame_max_frames": settings.frame_max_frames,
        }
        execution_hash = self.build_execution_hash(
            job_id=video.id,
            task_type=TASK_TYPE_PREPROCESSING,
            config_snapshot=config_snapshot,
        )
        task = Task(
            video_id=video.id,
            type=TASK_TYPE_PREPROCESSING,
            status=TaskStatus.pending,
            payload={
                "video_id": video.id,
                "video_path": video.file_path,
                "config_snapshot": config_snapshot,
                "frame_sampling_fps": config_snapshot["frame_sampling_fps"],
                "frame_max_frames": config_snapshot["frame_max_frames"],
                "execution_hash": execution_hash,
            },
        )
        self.db.add(task)
        self.db.flush()
        return task

    def initialize_preprocessing_pipeline(self, video: Video) -> Task:
        task = self.create_preprocessing_task(video)
        self.enqueue_task(task)
        person_task = self.create_person_task(video)
        self.enqueue_task(person_task)
        self.sync_video_status_from_task(video, task)
        return task

    def create_audio_task(self, video: Video, audio_path: str) -> Task:
        config_snapshot = {
            "whisper_model_name": settings.whisper_model_name,
        }
        execution_hash = self.build_execution_hash(
            job_id=video.id,
            task_type=TASK_TYPE_AUDIO,
            config_snapshot=config_snapshot,
        )
        task = Task(
            video_id=video.id,
            type=TASK_TYPE_AUDIO,
            status=TaskStatus.pending,
            payload={
                "video_id": video.id,
                "audio_path": audio_path,
                "config_snapshot": config_snapshot,
                "execution_hash": execution_hash,
            },
        )
        self.db.add(task)
        self.db.flush()
        return task

    def create_person_task(self, video: Video) -> Task:
        config_snapshot = {
            "person_model_name": settings.person_model_name,
            "person_conf_threshold": settings.person_conf_threshold,
            "person_track_iou_threshold": settings.person_track_iou_threshold,
            "frame_sampling_fps": settings.frame_sampling_fps,
        }
        execution_hash = self.build_execution_hash(
            job_id=video.id,
            task_type=TASK_TYPE_PERSON,
            config_snapshot=config_snapshot,
        )
        task = Task(
            video_id=video.id,
            type=TASK_TYPE_PERSON,
            status=TaskStatus.pending,
            payload={
                "video_id": video.id,
                "frames_dir": str(settings.frames_root_path / video.id),
                "config_snapshot": config_snapshot,
                "execution_hash": execution_hash,
            },
        )
        self.db.add(task)
        self.db.flush()
        return task

    def enqueue_task(self, task: Task) -> None:
        queue_name = None
        if task.type == TASK_TYPE_PREPROCESSING:
            queue_name = settings.preprocessing_queue_name
        elif task.type == TASK_TYPE_AUDIO:
            queue_name = settings.audio_queue_name
        elif task.type == TASK_TYPE_PERSON:
            queue_name = settings.person_queue_name
        if queue_name is None:
            raise ValueError(f"Unsupported queue routing for task type: {task.type}")
        queue_message = {"task_id": task.id, "video_id": task.video_id, "task_type": task.type}
        try:
            self.redis.lpush(queue_name, json.dumps(queue_message))
            task.status = TaskStatus.queued
        except RedisConnectionError as exc:
            task.status = TaskStatus.pending
            logger.warning(
                "task_enqueue_deferred",
                extra={
                    "task_id": task.id,
                    "job_id": task.video_id,
                    "worker": "orchestrator",
                    "status": task.status.value,
                    "error": str(exc),
                },
            )
        logger.info(
            "task_status_change",
            extra={
                "task_id": task.id,
                "job_id": task.video_id,
                "worker": "orchestrator",
                "status": task.status.value,
            },
        )
        self.db.flush()

    def mark_task_running(self, task: Task) -> None:
        task.status = TaskStatus.running
        task.started_at = datetime.utcnow()
        task.error_message = None
        logger.info(
            "task_status_change",
            extra={
                "task_id": task.id,
                "job_id": task.video_id,
                "worker": "preprocessing",
                "status": task.status.value,
            },
        )
        self.db.flush()

    def mark_task_success(self, task: Task, result: dict) -> None:
        task.status = TaskStatus.success
        task.result = result
        task.finished_at = datetime.utcnow()
        task.error_message = None
        logger.info(
            "task_status_change",
            extra={
                "task_id": task.id,
                "job_id": task.video_id,
                "worker": "preprocessing",
                "status": task.status.value,
            },
        )
        self.db.flush()

    def mark_task_failed(self, task: Task, error_message: str) -> None:
        task.status = TaskStatus.failed
        task.finished_at = datetime.utcnow()
        task.error_message = error_message
        logger.error(
            "task_status_change",
            extra={
                "task_id": task.id,
                "job_id": task.video_id,
                "worker": "preprocessing",
                "status": task.status.value,
                "error": error_message,
            },
        )
        self.db.flush()

    def mark_video_status(self, video: Video, status: VideoStatus, metadata_json: dict | None = None) -> None:
        video.status = status
        if metadata_json is not None:
            video.metadata_json = metadata_json
        self.db.flush()

    def sync_video_status_from_task(self, video: Video, task: Task) -> None:
        # Compute aggregate status across all tasks for this video so a single
        # task's success doesn't prematurely mark the video "completed" while
        # sibling tasks are still running.
        sibling_statuses = (
            self.db.execute(select(Task.status).where(Task.video_id == video.id)).scalars().all()
        )
        statuses = set(sibling_statuses) | {task.status}
        if TaskStatus.running in statuses:
            video.status = VideoStatus.processing
        elif TaskStatus.failed in statuses:
            video.status = VideoStatus.failed
        elif TaskStatus.pending in statuses or TaskStatus.queued in statuses:
            video.status = VideoStatus.queued
        elif statuses == {TaskStatus.success}:
            video.status = VideoStatus.completed
        self.db.flush()
