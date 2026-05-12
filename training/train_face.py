#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune or validate face recognition embeddings.")
    parser.add_argument("--config", default=str(ROOT / "training" / "configs" / "face.yaml"))
    parser.add_argument("--mode", choices=["train", "validate"], default="train")
    args = parser.parse_args()

    with Path(args.config).open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    output_dir = Path(cfg.get("output_dir", ROOT / "models" / "weights" / "face"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "validate":
        print("Run LFW pair verification against InsightFace embeddings in", output_dir)
        return 0

    print("Face fine-tuning uses InsightFace/ArcFace on VGGFace2 + MS-Celeb-1M cleaned subset.")
    print("Configure dataset roots in training/configs/face.yaml before launching full training.")
    print("Output directory:", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
