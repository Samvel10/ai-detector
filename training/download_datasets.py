#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "datasets" / "registry.yaml"


def load_registry() -> dict:
    with REGISTRY.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def download_coco(raw_root: Path) -> None:
    target = raw_root / "coco2017"
    target.mkdir(parents=True, exist_ok=True)
    try:
        from ultralytics import YOLO

        YOLO("yolov8n.pt").train(data="coco8.yaml", epochs=0, imgsz=640, device="cpu")
    except Exception as exc:
        print(f"Ultralytics COCO bootstrap skipped: {exc}")
    print(f"COCO target directory prepared at {target}")


def download_lfw(raw_root: Path) -> None:
    target = raw_root / "lfw"
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "lfw.tgz"
    if not archive.exists():
        urlretrieve("http://vis-www.cs.umass.edu/lfw/lfw.tgz", archive)
    if archive.suffixes[-2:] == [".t", ".gz"] or archive.suffix == ".tgz":
        subprocess.run(["tar", "-xzf", str(archive), "-C", str(target)], check=False)
    print(f"LFW prepared at {target}")


def download_ucf101(raw_root: Path) -> None:
    target = raw_root / "ucf101"
    target.mkdir(parents=True, exist_ok=True)
    print(
        "UCF101 requires manual download from https://www.crcv.ucf.edu/data/UCF101.php "
        f"into {target}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Download or prepare benchmark datasets.")
    parser.add_argument("--datasets", nargs="+", default=["coco", "lfw", "ucf101"])
    parser.add_argument("--raw-root", default=str(ROOT / "datasets" / "raw"))
    args = parser.parse_args()

    raw_root = Path(args.raw_root)
    raw_root.mkdir(parents=True, exist_ok=True)
    registry = load_registry()
    manifest = {"raw_root": str(raw_root), "datasets": args.datasets, "registry": registry}
    (raw_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for dataset in args.datasets:
        if dataset in {"coco", "coco2017", "coco_person"}:
            download_coco(raw_root)
        elif dataset == "lfw":
            download_lfw(raw_root)
        elif dataset == "ucf101":
            download_ucf101(raw_root)
        else:
            print(f"Dataset '{dataset}' is registered but requires manual acquisition. See datasets/registry.yaml.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
