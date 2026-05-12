import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _ROOT_DIR / "configs" / "default.json"


def _read_json_defaults() -> dict:
    if not _DEFAULT_CONFIG_PATH.exists():
        return {}

    with _DEFAULT_CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    storage_cfg = data.get("storage", {})
    redis_cfg = data.get("redis", {})
    frame_sampling_cfg = data.get("frame_sampling", {})
    return {
        "frame_sampling_fps": frame_sampling_cfg.get("fps", data.get("frame_sampling_fps")),
        "frame_max_frames": frame_sampling_cfg.get("max_frames", data.get("frame_max_frames")),
        "database_url": data.get("database_url"),
        "storage_root": storage_cfg.get("root"),
        "videos_dir": storage_cfg.get("videos_dir"),
        "audio_dir": storage_cfg.get("audio_dir"),
        "frames_dir": storage_cfg.get("frames_dir"),
        "redis_url": redis_cfg.get("url"),
        "preprocessing_queue_name": redis_cfg.get("preprocessing_queue_name"),
        "audio_queue_name": redis_cfg.get("audio_queue_name"),
        "person_queue_name": redis_cfg.get("person_queue_name"),
        "whisper_model_name": data.get("whisper_model_name"),
        "whisper_initial_prompt_hy": data.get("whisper_initial_prompt_hy"),
        "person_model_name": data.get("person_model_name"),
        "person_conf_threshold": data.get("person_conf_threshold"),
        "person_track_iou_threshold": data.get("person_track_iou_threshold"),
        "whisper_language_hint": data.get("whisper_language_hint"),
    }


_JSON_DEFAULTS = {k: v for k, v in _read_json_defaults().items() if v is not None}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Video Analysis Orchestrator"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str = _JSON_DEFAULTS.get("redis_url", "redis://localhost:6379/0")
    preprocessing_queue_name: str = _JSON_DEFAULTS.get("preprocessing_queue_name", "queue:preprocessing")
    audio_queue_name: str = _JSON_DEFAULTS.get("audio_queue_name", "queue:audio")
    person_queue_name: str = _JSON_DEFAULTS.get("person_queue_name", "queue:person")

    database_url: str = _JSON_DEFAULTS.get("database_url", "sqlite:///./app.db")

    storage_root: str = _JSON_DEFAULTS.get("storage_root", "storage")
    videos_dir: str = _JSON_DEFAULTS.get("videos_dir", "videos")
    audio_dir: str = _JSON_DEFAULTS.get("audio_dir", "audio")
    frames_dir: str = _JSON_DEFAULTS.get("frames_dir", "frames")

    frame_sampling_fps: int = Field(default=_JSON_DEFAULTS.get("frame_sampling_fps", 3), ge=1)
    frame_max_frames: int = Field(default=_JSON_DEFAULTS.get("frame_max_frames", 12000), ge=1)
    whisper_model_name: str = _JSON_DEFAULTS.get("whisper_model_name", "small")
    whisper_language_hint: str = _JSON_DEFAULTS.get("whisper_language_hint", "hy")
    whisper_initial_prompt_hy: str = _JSON_DEFAULTS.get(
        "whisper_initial_prompt_hy",
        "Սա հայերեն խոսք է գովազդային տեսանյութից։",
    )
    person_model_name: str = _JSON_DEFAULTS.get("person_model_name", "yolov8n.pt")
    person_conf_threshold: float = Field(default=_JSON_DEFAULTS.get("person_conf_threshold", 0.35), ge=0, le=1)
    person_track_iou_threshold: float = Field(
        default=_JSON_DEFAULTS.get("person_track_iou_threshold", 0.3), ge=0, le=1
    )

    @property
    def storage_root_path(self) -> Path:
        return Path(self.storage_root)

    @property
    def videos_root_path(self) -> Path:
        return self.storage_root_path / self.videos_dir

    @property
    def audio_root_path(self) -> Path:
        return self.storage_root_path / self.audio_dir

    @property
    def frames_root_path(self) -> Path:
        return self.storage_root_path / self.frames_dir


settings = Settings()
if not settings.redis_url:
    settings.redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/0"
