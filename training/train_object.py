#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune YOLO for person/object detection.")
    parser.add_argument("--config", default=str(ROOT / "training" / "configs" / "object.yaml"))
    args = parser.parse_args()

    with Path(args.config).open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    from ultralytics import YOLO

    base_weights = cfg.get("base_weights", "yolov8m.pt")
    data_yaml = cfg.get("data_yaml", "coco8.yaml")
    epochs = int(cfg.get("epochs", 50))
    imgsz = int(cfg.get("imgsz", 640))
    batch = int(cfg.get("batch", 16))
    device = cfg.get("device", "cuda")
    project = cfg.get("project", str(ROOT / "models" / "weights" / "object"))
    name = cfg.get("name", "yolo_finetune")

    model = YOLO(base_weights)
    model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=project,
        name=name,
        pretrained=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
