from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from redis import Redis
from sqlalchemy.orm import Session

from core.config import settings
from core.task_manager import TaskManager
from db.models import Video


class OrchestratorService:
    def __init__(self, db: Session, redis_client: Redis) -> None:
        self.db = db
        self.task_manager = TaskManager(db=db, redis_client=redis_client)

    def handle_video_upload(self, upload_file: UploadFile) -> dict:
        video_id = str(uuid4())
        video_dir = settings.videos_root_path / video_id
        video_dir.mkdir(parents=True, exist_ok=True)

        target_file_path = video_dir / "original.mp4"
        self._save_upload_file(upload_file=upload_file, target_path=target_file_path)

        video = Video(
            id=video_id,
            original_filename=upload_file.filename or "unknown.mp4",
            file_path=str(target_file_path),
            metadata_json={},
        )
        self.db.add(video)
        self.db.flush()

        preprocessing_task = self.task_manager.initialize_preprocessing_pipeline(video)

        self.db.commit()
        return {"video_id": video.id, "status": video.status.value, "task_id": preprocessing_task.id}

    @staticmethod
    def _save_upload_file(upload_file: UploadFile, target_path: Path) -> None:
        with target_path.open("wb") as out_file:
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                out_file.write(chunk)
