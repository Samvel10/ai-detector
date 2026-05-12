# Project Memory

## GitHub repository

- **Owner / name:** `Samvel10/ai-detector`
- **URL:** https://github.com/Samvel10/ai-detector
- **Local workspace:** `/home/samo/vidioAnalize`

This file is the canonical project memory. Every user question and assistant answer must be appended to `.memory/QA_LOG.md`. Every code or architecture change must be appended to `.memory/CHANGELOG.md`.

## Project purpose

Multimodal video analysis platform: upload video, run preprocessing, audio transcription, person/object/face/action detection, persist events, expose API and React dashboard.

## Current architecture

- **API:** FastAPI (`api/main.py`)
- **Orchestrator:** upload and task creation (`orchestrator/service.py`)
- **Workers:** preprocessing, audio (Whisper), person/vision (`workers/`)
- **Storage:** SQLite + Redis queues + filesystem under `storage/`
- **Frontend:** React/Vite dashboard (`intelligence-dashboard/`)
- **Model quality layer:** `models/`, `datasets/`, `training/`

## Model quality domains

| Domain | Default inference | Training entrypoint | Datasets |
| --- | --- | --- | --- |
| Face recognition | InsightFace ArcFace (`buffalo_l`) | `training/train_face.py` | VGGFace2, MS-Celeb-1M subset, LFW |
| Person detection / tracking | YOLOv8 + ByteTrack | `training/train_object.py` | COCO person, CrowdHuman, MOT17/20 |
| Object detection | YOLOv8 | `training/train_object.py` | COCO, Open Images |
| Action / motion | Video classifier (R3D / SlowFast path) | `training/train_action.py` | Kinetics-400/700, UCF101, HMDB51 |

## Operational notes

- GPU is used when available; CPU fallback is supported.
- Large artifacts (weights, raw datasets, uploaded videos) stay out of git via `.gitignore`.
- Synthetic analysis in `api/main.py` exists for demos; production path uses real workers.

## Memory maintenance rules

1. Record each user question and assistant answer in `QA_LOG.md`.
2. Record each implementation change in `CHANGELOG.md`.
3. Keep this file aligned with repository name and high-level architecture.
