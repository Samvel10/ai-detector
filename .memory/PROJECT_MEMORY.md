# Project Memory

## GitHub repository

- **Owner / name:** `Samvel10/ai-detector`
- **URL:** https://github.com/Samvel10/ai-detector
- **Default working branch:** `Samo`
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

## Runtime (CPU-only)

- Python 3.12 venv at `.venv/` (recreate with `uv venv .venv --python 3.12` if missing).
- Install: `uv pip install --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu torch torchvision` then `uv pip install --python .venv/bin/python -r requirements.txt`.
- Auto-downloaded model weights on first person-task run (cached after):
  - `yolov8m.pt` (50 MB) — project root
  - `~/.insightface/models/buffalo_l/` (276 MB)
  - `~/.cache/torch/hub/checkpoints/r3d_18-*.pth` (127 MB, Kinetics-400)
- Local services:
  - Redis: `redis-server` listening on `:6379` (no persistence needed).
  - API: `uvicorn api.main:app --host 127.0.0.1 --port 8000`.
  - Workers: `python -m workers.{preprocessing,audio,person}.worker` (one process each).

## Pipeline verification status (2026-05-14)

Tested end-to-end with three real videos. All three reach terminal status:

| Video | Result |
| --- | --- |
| `IMG_1879.MP4` (14.9 s, has audio) | Person + face + action detected; no spurious speech segments (audio is noise). |
| `video_2026-05-11_17-27-29.mp4` (17.6 s, near-silent UI recording) | Correctly reports 0 person tracks (no people in screen recording). |
| `7261920-uhd_2160_3840_25fps.mp4` (40.7 s 4K, no audio stream) | Person + face tracked entire 40 s; preprocessing skips audio cleanly. |

## Known model-accuracy limitations

These are model-quality issues, not pipeline bugs — they need labeled training data to fix properly:

- **Action recognition**: R3D + Kinetics-400 has no class for "person sitting at desk talking", "screen recording", etc. Low-confidence labels like `tossing coin` (0.38) appear; the score correctly reflects uncertainty.
- **Object detection**: generic COCO-trained YOLOv8m produces high-confidence false positives on bathroom/studio scenes (e.g. `microwave` at 0.94 on a beard-trimming closeup). Pipeline now aggregates these by track so the noise is bounded, but the labels themselves are wrong.
- **Face identity**: every face is `identity=unknown` — there is no enrolled face database yet, only 512-d embeddings.
- **Whisper transcription quality**: when the source has no speech, Whisper hallucinates repetitive tokens; pipeline gates these via `no_speech_prob`, `compression_ratio`, and a token-uniqueness check.

## Memory maintenance rules

1. Record each user question and assistant answer in `QA_LOG.md`.
2. Record each implementation change in `CHANGELOG.md`.
3. Keep this file aligned with repository name and high-level architecture.
