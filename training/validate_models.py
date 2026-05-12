#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate upgraded model backends.")
    parser.add_argument("--output", default=str(ROOT / "models" / "weights" / "validation_report.json"))
    args = parser.parse_args()

    report: dict[str, object] = {}
    try:
        from models.pipeline import VisionPipeline

        pipeline = VisionPipeline()
        report["detector"] = {"ready": pipeline.detector.model is not None}
        report["face"] = {"ready": pipeline.face.ready}
        report["action"] = {"ready": pipeline.action.ready}
    except Exception as exc:
        report["error"] = str(exc)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
