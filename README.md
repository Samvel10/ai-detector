# AI Video Analysis - Step 1 Foundation

This project implements a production foundation for video analysis orchestration with audio and person intelligence:

- FastAPI orchestrator API
- Task system with status lifecycle
- Redis queue integration (`queue:preprocessing`)
- Preprocessing worker (FFmpeg audio + frames extraction)
- Audio worker (Whisper multilingual speech-to-text)
- Person worker (YOLO person detection + temporal tracking)

## Implemented Components

- `api/main.py`: upload API and job status API.
- `orchestrator/service.py`: upload handling + task creation.
- `core/task_manager.py`: task lifecycle updates and queueing.
- `core/config.py`: centralized settings from environment.
- `workers/preprocessing/worker.py`: async preprocessing worker loop.
- `workers/audio/worker.py`: async Whisper transcription worker loop.
- `workers/person/worker.py`: async person detection and tracking worker loop.
- `db/models.py`, `db/session.py`: persistent state for videos and tasks.

## Project Structure

```text
project/
├── api/
├── orchestrator/
├── workers/
│   └── preprocessing/
├── core/
│   ├── task_manager.py
│   └── config.py
├── storage/
├── db/
├── configs/
└── README.md
```

## Prerequisites

- Python 3.11+
- Redis server
- FFmpeg + FFprobe binaries available in PATH

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Prepare environment file:

   ```bash
   cp .env.example .env
   ```

3. Start Redis (example):

   ```bash
   redis-server
   ```

## Run Services

Run API server:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Run preprocessing worker (separate terminal):

```bash
python -m workers.preprocessing.worker
```

Run audio worker (separate terminal):

```bash
python -m workers.audio.worker
```

Run person worker (separate terminal):

```bash
python -m workers.person.worker
```

## API Endpoints

### `POST /upload-video`

- form-data field: `file` (video file)
- behavior:
  1. stores video to `storage/videos/{video_id}/original.mp4`
  2. creates `videos` DB record
  3. creates preprocessing task
  4. enqueues task to Redis `queue:preprocessing`
- response:

```json
{
  "video_id": "uuid",
  "status": "queued"
}
```

### `GET /videos/{video_id}`

Returns video status, metadata, and task statuses.

## Worker Processing Behavior

For each preprocessing task:

1. Marks task `running` and video `processing`
2. Extracts audio:
   - output: `storage/audio/{video_id}/audio.wav`
3. Extracts frames at configured FPS (default 3):
   - output: `storage/frames/{video_id}/frame_XXXX.jpg`
4. Probes audio duration with FFprobe
5. Stores task result:
   - `frame_count`
   - `audio_duration_sec`
6. Marks task `success` and video `completed`
7. Creates and enqueues audio task after preprocessing success

For each audio task:

1. Verifies extracted audio file exists
2. Runs Whisper transcription with automatic language detection
3. Supports Armenian, Russian, and English transcription
4. Stores segment-level transcript output in task result
5. Emits `speech_segment` events through EventManager
6. Marks audio task `success`

For each person task:

1. Waits for preprocessing completion and verifies extracted frames exist
2. Runs YOLO person detection on extracted frames
3. Tracks detections over time with stable `track_id` continuity (IoU-based)
4. Stores tracks with `track_id`, `start_sec`, `end_sec`, `boxes`, `confidence`
5. Emits visual timeline events through EventManager:
   - `person_detected`
   - `person_track_start`
   - `person_track_end`

On failure:

- marks task `failed`
- marks video `failed`
- saves error message in task row

## Task Status Lifecycle

- `pending`
- `queued`
- `running`
- `success`
- `failed`

## Test Scenario

1. Start Redis.
2. Start API server.
3. Start preprocessing worker.
4. Upload a test video:

   ```bash
   curl -X POST "http://localhost:8000/upload-video" \
     -F "file=@/absolute/path/to/test.mp4"
   ```

5. Read returned `video_id`.
6. Poll status:

   ```bash
   curl "http://localhost:8000/videos/{video_id}"
   ```

Expected outcome:

- `status: completed`
- one preprocessing task with `status: success`
- files exist:
  - `storage/videos/{video_id}/original.mp4`
  - `storage/audio/{video_id}/audio.wav`
  - `storage/frames/{video_id}/frame_XXXX.jpg`

