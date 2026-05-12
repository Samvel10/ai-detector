from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import torch

_ROOT = Path(__file__).resolve().parent.parent
_MODELS_CONFIG = _ROOT / "configs" / "models.json"


@lru_cache(maxsize=1)
def load_models_config() -> dict:
    if not _MODELS_CONFIG.exists():
        return {}
    with _MODELS_CONFIG.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_device(prefer_gpu: bool | None = None) -> str:
    cfg = load_models_config().get("device", {})
    use_gpu = cfg.get("prefer_gpu", True) if prefer_gpu is None else prefer_gpu
    if use_gpu and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def resolve_batch_size(default: int = 8) -> int:
    cfg = load_models_config().get("device", {})
    return int(cfg.get("batch_size", default))


def weights_path(*parts: str) -> Path:
    return _ROOT.joinpath(*parts)


def first_existing_path(*candidates: str) -> Path | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_absolute():
            path = _ROOT / path
        if path.exists():
            return path
    return None
