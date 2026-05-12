from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DatasetSpec:
    name: str
    root: Path
    split: str = "train"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
