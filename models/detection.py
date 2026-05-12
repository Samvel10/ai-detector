from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from models.common import first_existing_path, load_models_config, resolve_batch_size, resolve_device

logger = logging.getLogger("video_analysis.models.detection")

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - optional runtime dependency
    YOLO = None  # type: ignore[assignment,misc]


@dataclass
class Detection:
    cls_id: int
    label: str
    confidence: float
    bbox: list[float]
    track_id: str | None = None


@dataclass
class FrameDetections:
    frame_path: Path
    timestamp_sec: float
    frame_width: int
    frame_height: int
    detections: list[Detection]


class YoloVisionDetector:
    def __init__(self) -> None:
        self._model = None
        self._tracker = "bytetrack.yaml"
        self._person_class_id = 0
        self._conf = 0.35
        self._iou = 0.45
        self._init_from_config()

    def _init_from_config(self) -> None:
        if YOLO is None:
            raise RuntimeError("Ultralytics is not installed.")
        cfg = load_models_config().get("person_object", {})
        self._tracker = str(cfg.get("tracker", "bytetrack.yaml"))
        self._person_class_id = int(cfg.get("person_class_id", 0))
        self._conf = float(cfg.get("conf_threshold", 0.35))
        self._iou = float(cfg.get("iou_threshold", 0.45))
        weights = first_existing_path(
            str(cfg.get("fine_tuned_weights", "")),
            str(cfg.get("base_weights", "yolov8m.pt")),
        )
        if weights is None:
            weights = Path("yolov8m.pt")
        self._model = YOLO(str(weights))
        device = resolve_device()
        if device == "cuda":
            self._model.to(device)

    @property
    def model(self):
        if self._model is None:
            raise RuntimeError("YOLO model is not initialized.")
        return self._model

    def track_frame(self, frame_path: Path, timestamp_sec: float, persist: bool = True) -> FrameDetections:
        result = self.model.track(
            source=str(frame_path),
            conf=self._conf,
            iou=self._iou,
            tracker=self._tracker,
            persist=persist,
            verbose=False,
        )[0]
        names = result.names if hasattr(result, "names") else {}
        frame_h, frame_w = (0, 0)
        if hasattr(result, "orig_shape") and result.orig_shape:
            frame_h, frame_w = int(result.orig_shape[0]), int(result.orig_shape[1])
        detections: list[Detection] = []
        boxes = result.boxes
        if boxes is not None and boxes.xyxy is not None:
            for idx in range(len(boxes.xyxy)):
                cls_id = int(boxes.cls[idx].item())
                bbox = [float(v) for v in boxes.xyxy[idx].tolist()]
                conf = float(boxes.conf[idx].item())
                track_id = None
                if boxes.id is not None:
                    track_id = f"p-{int(boxes.id[idx].item())}"
                detections.append(
                    Detection(
                        cls_id=cls_id,
                        label=str(names.get(cls_id, f"class_{cls_id}")),
                        confidence=conf,
                        bbox=bbox,
                        track_id=track_id,
                    )
                )
        return FrameDetections(
            frame_path=frame_path,
            timestamp_sec=timestamp_sec,
            frame_width=frame_w,
            frame_height=frame_h,
            detections=detections,
        )

    def predict_batch(self, frame_paths: list[Path], timestamps: list[float]) -> list[FrameDetections]:
        if not frame_paths:
            return []
        batch_size = max(1, resolve_batch_size())
        outputs: list[FrameDetections] = []
        for start in range(0, len(frame_paths), batch_size):
            chunk_paths = frame_paths[start : start + batch_size]
            chunk_ts = timestamps[start : start + batch_size]
            results = self.model.predict(
                source=[str(path) for path in chunk_paths],
                conf=self._conf,
                iou=self._iou,
                verbose=False,
            )
            for frame_path, timestamp_sec, result in zip(chunk_paths, chunk_ts, results, strict=True):
                names = result.names if hasattr(result, "names") else {}
                frame_h, frame_w = (0, 0)
                if hasattr(result, "orig_shape") and result.orig_shape:
                    frame_h, frame_w = int(result.orig_shape[0]), int(result.orig_shape[1])
                detections: list[Detection] = []
                boxes = result.boxes
                if boxes is not None and boxes.xyxy is not None:
                    for idx in range(len(boxes.xyxy)):
                        cls_id = int(boxes.cls[idx].item())
                        detections.append(
                            Detection(
                                cls_id=cls_id,
                                label=str(names.get(cls_id, f"class_{cls_id}")),
                                confidence=float(boxes.conf[idx].item()),
                                bbox=[float(v) for v in boxes.xyxy[idx].tolist()],
                            )
                        )
                outputs.append(
                    FrameDetections(
                        frame_path=frame_path,
                        timestamp_sec=timestamp_sec,
                        frame_width=frame_w,
                        frame_height=frame_h,
                        detections=detections,
                    )
                )
        return outputs
