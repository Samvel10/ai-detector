from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import torch
import torch.nn.functional as F

from models.common import first_existing_path, load_models_config, resolve_device

logger = logging.getLogger("video_analysis.models.action")

try:
    import cv2
except Exception:  # pragma: no cover - optional runtime dependency
    cv2 = None  # type: ignore[assignment]

try:
    from torchvision.models.video import R3D_18_Weights, r3d_18
except Exception:  # pragma: no cover - optional runtime dependency
    R3D_18_Weights = None  # type: ignore[assignment,misc]
    r3d_18 = None  # type: ignore[assignment]


@dataclass
class ActionPrediction:
    label: str
    confidence: float
    source: str


class ActionRecognizer:
    def __init__(self) -> None:
        self._model = None
        self._labels: list[str] = []
        self._clip_frames = 16
        self._clip_stride = 2
        self._ready = False
        self._device = resolve_device()
        self._init_from_config()

    def _init_from_config(self) -> None:
        cfg = load_models_config().get("action", {})
        self._clip_frames = int(cfg.get("clip_frames", 16))
        self._clip_stride = int(cfg.get("clip_stride", 2))
        custom_weights = first_existing_path(str(cfg.get("base_weights", "")))
        if r3d_18 is None:
            logger.warning("torchvision_video_models_unavailable")
            return
        if custom_weights is not None:
            model = r3d_18(weights=None)
            checkpoint = torch.load(custom_weights, map_location=self._device)
            state_dict = checkpoint.get("state_dict", checkpoint)
            model.load_state_dict(state_dict, strict=False)
            self._labels = list(checkpoint.get("labels", []))
        else:
            weights_enum = R3D_18_Weights.KINETICS400_V1 if R3D_18_Weights is not None else None
            model = r3d_18(weights=weights_enum)
            meta = weights_enum.meta if weights_enum is not None else {}
            self._labels = list(meta.get("categories", []))
        model.eval()
        model.to(self._device)
        self._model = model
        self._ready = True

    @property
    def ready(self) -> bool:
        return self._ready

    def _load_clip_tensor(self, frame_paths: list[Path]) -> torch.Tensor | None:
        if cv2 is None or not frame_paths:
            return None
        sampled = frame_paths[:: max(1, self._clip_stride)]
        if len(sampled) > self._clip_frames:
            sampled = sampled[: self._clip_frames]
        frames = []
        for frame_path in sampled:
            frame = cv2.imread(str(frame_path))
            if frame is None:
                continue
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (112, 112))
            frames.append(torch.from_numpy(frame).permute(2, 0, 1).float() / 255.0)
        if len(frames) < 4:
            return None
        while len(frames) < self._clip_frames:
            frames.append(frames[-1])
        clip = torch.stack(frames[: self._clip_frames], dim=1)
        return clip.unsqueeze(0)

    def predict_track(self, frame_paths: list[Path]) -> ActionPrediction | None:
        if not self._ready or self._model is None:
            return None
        clip = self._load_clip_tensor(frame_paths)
        if clip is None:
            return None
        clip = clip.to(self._device)
        with torch.no_grad():
            logits = self._model(clip)
            probs = F.softmax(logits, dim=1)[0]
            score, index = torch.max(probs, dim=0)
        label = self._labels[int(index)] if self._labels else f"class_{int(index)}"
        return ActionPrediction(label=label, confidence=float(score.item()), source="action.r3d")
