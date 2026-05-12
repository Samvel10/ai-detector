# Changelog

## 2026-05-12 (branch workflow)

- Switched local development workflow to GitHub branch `Samo` (`origin/Samo`).

- Created `.memory/` project memory (`PROJECT_MEMORY.md`, `CHANGELOG.md`, `QA_LOG.md`).
- Documented GitHub repository `Samvel10/ai-detector`.
- Added real model-quality pipeline layout: `models/`, `datasets/`, `training/`.
- Added dataset download and training scripts for face, object, and action domains.
- Added model and training configuration files under `configs/` and `training/configs/`.
- Integrated upgraded vision inference into `workers/person/worker.py` (YOLO + ByteTrack + InsightFace + action model path).
- Prepared repository push to GitHub with `.gitignore` excluding runtime artifacts and dependencies.
- Pushed full project to `https://github.com/Samvel10/ai-detector` on branch `main`.
