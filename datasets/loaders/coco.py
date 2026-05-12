from __future__ import annotations

from pathlib import Path

from datasets.loaders.base import DatasetSpec, ensure_dir


def coco_dataset(root: Path, split: str = "train") -> DatasetSpec:
    ensure_dir(root)
    return DatasetSpec(name="coco2017", root=root / "coco2017", split=split)


def open_images_dataset(root: Path) -> DatasetSpec:
    ensure_dir(root)
    return DatasetSpec(name="openimages", root=root / "openimages")


def lfw_dataset(root: Path) -> DatasetSpec:
    ensure_dir(root)
    return DatasetSpec(name="lfw", root=root / "lfw", split="val")


def ucf101_dataset(root: Path) -> DatasetSpec:
    ensure_dir(root)
    return DatasetSpec(name="ucf101", root=root / "ucf101", split="train")
