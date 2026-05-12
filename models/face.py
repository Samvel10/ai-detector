from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from models.common import load_models_config, resolve_device

logger = logging.getLogger("video_analysis.models.face")

try:
    from insightface.app import FaceAnalysis
except Exception:  # pragma: no cover - optional runtime dependency
    FaceAnalysis = None  # type: ignore[assignment,misc]


@dataclass
class FaceDetection:
    bbox: list[float]
    confidence: float
    embedding: list[float] | None = None
    identity: str = "unknown"


class FaceRecognizer:
    def __init__(self) -> None:
        self._app = None
        self._threshold = 0.5
        self._ready = False
        self._init_from_config()

    def _init_from_config(self) -> None:
        cfg = load_models_config().get("face", {})
        self._threshold = float(cfg.get("detection_threshold", 0.5))
        if FaceAnalysis is None:
            logger.warning("insightface_unavailable")
            return
        model_pack = str(cfg.get("model_pack", "buffalo_l"))
        device_id = 0 if resolve_device() == "cuda" else -1
        app = FaceAnalysis(name=model_pack, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        app.prepare(ctx_id=device_id, det_size=(640, 640))
        self._app = app
        self._ready = True

    @property
    def ready(self) -> bool:
        return self._ready

    def detect_in_person_crop(self, frame_bgr: np.ndarray, person_bbox: list[float]) -> FaceDetection | None:
        if not self._ready or self._app is None:
            return None
        x1, y1, x2, y2 = [int(max(0, round(v))) for v in person_bbox]
        if x2 <= x1 or y2 <= y1:
            return None
        crop = frame_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        faces = self._app.get(crop)
        if not faces:
            return None
        best = max(faces, key=lambda face: float(getattr(face, "det_score", 0.0)))
        score = float(getattr(best, "det_score", 0.0))
        if score < self._threshold:
            return None
        fx1, fy1, fx2, fy2 = [float(v) for v in best.bbox.tolist()]
        bbox = [x1 + fx1, y1 + fy1, x1 + fx2, y1 + fy2]
        embedding = None
        if getattr(best, "embedding", None) is not None:
            embedding = [float(v) for v in best.embedding.tolist()]
        return FaceDetection(bbox=bbox, confidence=score, embedding=embedding)

    def detect_in_frame(self, frame_path: Path, person_bbox: list[float]) -> FaceDetection | None:
        try:
            import cv2
        except Exception:
            return None
        frame = cv2.imread(str(frame_path))
        if frame is None:
            return None
        return self.detect_in_person_crop(frame, person_bbox)
