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

## 2026-05-14 (pipeline E2E + bug fixes)

End-to-end verification on three real videos (`IMG_1879.MP4`, `video_2026-05-11_17-27-29.mp4`, `7261920-uhd_2160_3840_25fps.mp4`). Found and fixed seven pipeline bugs:

1. `workers/audio/worker.py` — Whisper language was hardcoded to `hy` (Armenian). Now reads `whisper_language_hint` from config; treats `auto`/empty as Whisper auto-detect. Default in `configs/default.json` is now `"auto"`.
2. `workers/audio/worker.py` — Added `_is_speech_segment` gate that checks Whisper's own `no_speech_prob` (>0.6) and `compression_ratio` (>2.4); also detects single-character repetition (e.g. "Ə Ə Ə..."). Low-quality segments no longer emitted as events, only kept in the task result for debugging.
3. `workers/audio/worker.py` — `condition_on_previous_text=False` to reduce hallucination across segments.
4. `models/pipeline.py` — Aggregate object detections by `(label, track_id)` so 34 per-frame "microwave" detections become 1 event with `observation_count=34`, `first_seen_sec`, `last_seen_sec`. Added `object_conf_threshold` (default 0.55) read from `configs/models.json` under `person_object`. Object false-positives are now bounded.
5. `core/task_manager.py` — `sync_video_status_from_task` now computes aggregate status across all sibling tasks instead of mirroring one task. Video no longer flips to `completed` while a sibling is still running.
6. `workers/person/worker.py` — Sync video status after marking person task success (was missing; meant video stayed `processing` forever when person was the last task to finish).
7. `workers/preprocessing/worker.py` — Probe source for an audio stream before extracting; videos without audio (like 4K stock footage) no longer fail the entire preprocessing task. `audio_extracted` event and audio task are only created when audio is present.
8. `workers/person/worker.py` — Stop infinitely re-queueing when preprocessing has `failed`; mark the person task failed too so the video reaches a terminal state.
9. `.gitignore` — Added `graphify-out/` (knowledge-graph build artifacts).
10. Added `.claude/` project-scoped hooks (UserPromptSubmit + Stop) that auto-log every Q&A to `.memory/QA_LOG.md` and auto-push to `origin/Samo`. Triggered by keyword `memory` in any user prompt.
