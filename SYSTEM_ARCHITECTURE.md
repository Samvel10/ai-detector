# AI Video Analysis System Architecture Blueprint

## 1) Purpose and Scope

This document defines a production-grade, modular AI video analysis platform that ingests videos (1 minute to 1+ hour), analyzes audio and visual streams, tracks people and faces over time, detects objects, and produces a unified temporal understanding timeline.

This file is the single source of truth for system architecture before implementation.

### Primary Outcomes

- Transform raw video into structured, searchable events.
- Preserve temporal relationships across modalities (speech, people, faces, objects, actions).
- Maintain extensibility: add/remove workers and models with minimal impact.
- Support CPU-first deployment with later GPU acceleration.
- Support offline learning from user feedback, without real-time model mutation.

### Non-Goals (Initial Version)

- No real-time streaming inference requirement.
- No online learning updates during active job execution.
- No hard dependency on a single model provider.

---

## 2) High-Level System Architecture

The platform is organized as an orchestrated asynchronous pipeline:

1. **Ingest Layer** receives a video and creates a job.
2. **Orchestrator** decomposes the job into modular tasks.
3. **Redis Queue** dispatches tasks to specialized workers.
4. **Workers** process independent modalities and emit normalized events.
5. **Temporal Engine** fuses events into a coherent timeline.
6. **Storage Layer** persists raw assets, metadata, entities, and events.
7. **Feedback/Learning Pipeline** consumes corrections for offline retraining.

### Macro Diagram (ASCII)

```text
                   +------------------------+
                   |   Client / API Layer   |
                   +-----------+------------+
                               |
                               v
                    +----------+-----------+
                    |      Orchestrator    |
                    | (Job + Task Control) |
                    +----------+-----------+
                               |
             +-----------------+------------------+
             |                                    |
             v                                    v
   +---------+----------+              +----------+---------+
   | PostgreSQL (state) |              | Redis Queue/State  |
   | jobs/tasks/entities|              | pending/running    |
   +---------+----------+              +----------+---------+
             |                                    |
             |                                    v
             |                    +---------------+------------------+
             |                    |           Worker Pool            |
             |                    | audio/person/face/object/action |
             |                    +---+--------+--------+--------+---+
             |                        |        |        |        |
             |                        v        v        v        v
             |                   +------------------------------------+
             +------------------>|      Temporal Fusion Engine        |
                                 |   event normalization + merging    |
                                 +----------------+-------------------+
                                                  |
                                                  v
                                 +----------------+-------------------+
                                 |   Structured Results + Timeline    |
                                 | Postgres + JSON export + indexing  |
                                 +------------------------------------+
```

---

## 3) Core Design Principles

1. **Modularity First**  
   Every analytical capability is isolated as a worker with a strict contract.

2. **Event-Centric Data Model**  
   All outputs are converted into timestamped, typed events with confidence and provenance.

3. **Asynchronous, Fault-Isolated Execution**  
   Workers fail independently; orchestrator retries or degrades gracefully.

4. **Deterministic Reproducibility**  
   Every job stores model versions, config snapshot, and task run metadata.

5. **CPU-First, GPU-Optional**  
   Model runtime adapter chooses device per policy/config without changing business logic.

6. **Schema Stability + Versioning**  
   Output schemas include `schema_version` and per-model `model_version`.

---

## 4) Component Breakdown

## 4.1 Orchestrator

### Responsibilities

- Accept analysis requests and register `video` records.
- Generate task graph from enabled modules.
- Push tasks to Redis queues.
- Track task dependencies and lifecycle.
- Trigger Temporal Engine when prerequisite tasks complete.
- Handle retries, dead-letter routing, timeout policies.

### Orchestrator Inputs

- Video metadata (path, checksum, duration, resolution, fps).
- User/system configuration snapshot.
- Feature toggles (workers enabled/disabled).

### Orchestrator Outputs

- Task records in PostgreSQL.
- Queue messages in Redis.
- Job-level status transitions.
- Final analysis artifact references.

### Orchestrator State Machine (Job-Level)

```text
created -> queued -> processing -> merging -> completed
                         |             |
                         v             v
                      partial       failed
```

- **partial**: one or more workers failed but minimum required outputs exist.
- **failed**: critical tasks failed and no viable timeline can be produced.

---

## 4.2 Task System

Every processing unit is represented as a task with normalized lifecycle.

### Task Entity Fields

- `id` (UUID)
- `job_id` (UUID)
- `type` (audio, person, face, object, action, temporal_merge, export)
- `status` (pending, queued, running, succeeded, failed, retrying, cancelled, dead_letter)
- `priority` (int)
- `attempt` (int)
- `max_attempts` (int)
- `depends_on` (array of task IDs)
- `payload` (JSON)
- `worker_hint` (optional target queue/runtime)
- `started_at`, `finished_at`
- `error_code`, `error_message`
- `created_at`, `updated_at`

### Task Lifecycle

```text
pending -> queued -> running -> succeeded
                    |   |
                    |   +-> failed -> retrying -> queued
                    |
                    +-> cancelled

failed (max attempts reached) -> dead_letter
```

### Retry Policy Guidance

- Retry transient failures (I/O, temporary model load failure, queue timeout).
- Do not retry deterministic data failures repeatedly (corrupt file, unsupported codec) without transformation step.
- Use exponential backoff with jitter.

---

## 4.3 Queue System (Redis)

Redis is used for:

1. **Task queues** (per worker type, optionally per priority).
2. **Ephemeral state** (locks, heartbeats, progress, in-flight metadata).
3. **Idempotency guards** (dedupe keys).

### Recommended Queue Names

- `queue:audio`
- `queue:person`
- `queue:face`
- `queue:object`
- `queue:action`
- `queue:temporal`
- `queue:dead_letter`

### Redis Key Categories

- `task:lock:{task_id}` (task claim lock)
- `job:progress:{job_id}` (percentage + phase)
- `worker:heartbeat:{worker_id}`
- `idempotency:{job_id}:{task_type}:{hash}`

### Queue Message Envelope (JSON Example)

```json
{
  "message_id": "uuid",
  "task_id": "uuid",
  "job_id": "uuid",
  "task_type": "audio",
  "attempt": 1,
  "enqueued_at": "2026-04-28T20:00:00Z",
  "trace_id": "uuid",
  "payload_ref": "postgres://tasks/uuid"
}
```

---

## 4.4 Worker Modules

Workers are independently deployable services with shared base interfaces:

- `validate_input`
- `load_models`
- `process`
- `emit_outputs`
- `emit_events`
- `cleanup`

Each worker writes:

1. Raw modality outputs (files/JSON artifacts)
2. Normalized events for Temporal Engine
3. Entity updates (persons, objects, face identities)

---

### 4.4.1 Audio Worker (FFmpeg + Whisper)

#### Purpose

- Extract audio track.
- Perform ASR transcription in Armenian, Russian, English.
- Produce sentence-level timestamps.

#### Inputs

- Video file path.
- Audio extraction config (sample rate, channels, format).
- Whisper config (model size, language mode, beam settings).

#### Processing Logic

1. Validate media readability.
2. Extract audio via FFmpeg (canonical WAV/PCM preferred).
3. Run Whisper inference:
   - language auto-detect or configured language set
   - sentence segmentation
4. Normalize timestamps to video timeline.
5. Emit transcript segments with confidence.

#### Outputs

- `audio/transcript.json`
- Sentence events in `events` table (`event_type = speech_segment`)

#### Output JSON Example

```json
{
  "schema_version": "1.0",
  "job_id": "uuid",
  "language_detected": "ru",
  "segments": [
    {
      "segment_id": "seg-001",
      "start_sec": 3.20,
      "end_sec": 5.10,
      "text": "Привет, как дела?",
      "confidence": 0.93
    }
  ],
  "model": {
    "name": "whisper-large-v3",
    "version": "2026.01"
  }
}
```

---

### 4.4.2 Person Worker (YOLOv8 + Tracking)

#### Purpose

- Detect all persons in frames.
- Track each person across time with consistent person track IDs.

#### Inputs

- Video path.
- Sampling policy (all frames / stride).
- Detector config (confidence threshold, NMS threshold).
- Tracker config (DeepSORT/ByteTrack parameters).

#### Processing Logic

1. Decode frames (or stream decode).
2. Run YOLOv8 person class detection.
3. Associate detections frame-to-frame with tracker.
4. Generate stable `track_id` for each person.
5. Emit per-frame detections + track intervals.

#### Outputs

- `vision/person_tracks.json`
- Person entities in `persons` table
- Events: `person_appeared`, `person_present`, `person_disappeared`

#### Output JSON Example

```json
{
  "schema_version": "1.0",
  "job_id": "uuid",
  "tracks": [
    {
      "track_id": "p-12",
      "start_sec": 1.04,
      "end_sec": 58.90,
      "boxes": [
        { "t": 1.04, "x1": 120, "y1": 88, "x2": 330, "y2": 480, "conf": 0.95 }
      ]
    }
  ],
  "model": {
    "name": "yolov8m",
    "version": "8.x"
  }
}
```

---

### 4.4.3 Face Worker (InsightFace / DeepFace)

#### Purpose

- Detect faces in person regions or full frames.
- Generate embeddings.
- Cluster and re-identify the same person over time.

#### Inputs

- Frame references or person track crops.
- Face detector/aligner config.
- Embedding model selection (InsightFace/DeepFace backend).
- Similarity thresholds.

#### Processing Logic

1. Run face detection and alignment.
2. Compute embeddings per face instance.
3. Perform incremental identity association (embedding similarity + temporal constraints).
4. Map face identities to person tracks when overlapping.
5. Persist embedding metadata (and secure storage pointer for vectors).

#### Outputs

- `vision/faces.json`
- Face-linked identity references in `persons`
- Events: `face_detected`, `identity_matched`, `identity_uncertain`

#### Output JSON Example

```json
{
  "schema_version": "1.0",
  "job_id": "uuid",
  "faces": [
    {
      "face_id": "f-341",
      "time_sec": 4.21,
      "bbox": { "x1": 220, "y1": 130, "x2": 300, "y2": 220 },
      "embedding_ref": "embeddings/job-uuid/f-341.npy",
      "identity_cluster_id": "id-07",
      "match_confidence": 0.88,
      "linked_track_id": "p-12"
    }
  ],
  "model": {
    "name": "insightface-arcface",
    "version": "latest-stable"
  }
}
```

---

### 4.4.4 Object Worker (YOLOv8 Customizable)

#### Purpose

- Detect scene objects (table, phone, cup, etc.).
- Track object presence over time (optional per class).

#### Inputs

- Video/frame stream.
- Object class set and confidence thresholds.
- Model variant (general/custom).

#### Processing Logic

1. Run object detection on sampled frames.
2. Optional temporal smoothing and class-specific tracking.
3. Emit object instances with timestamps and optional track IDs.

#### Outputs

- `vision/objects.json`
- Object entities in `objects` table
- Events: `object_detected`, `object_present`, `object_moved` (if tracked)

#### Output JSON Example

```json
{
  "schema_version": "1.0",
  "job_id": "uuid",
  "objects": [
    {
      "object_instance_id": "o-991",
      "class": "phone",
      "time_sec": 4.10,
      "bbox": { "x1": 410, "y1": 330, "x2": 470, "y2": 410 },
      "confidence": 0.91
    }
  ],
  "model": {
    "name": "yolov8l-custom",
    "version": "objects-v2"
  }
}
```

---

### 4.4.5 Action Worker (Future: SlowFast / Video Transformer)

#### Purpose

- Detect temporally extended actions (pushing, dropping objects, etc.).

#### Inputs

- Video clips or track-centered clips.
- Action class taxonomy.
- Temporal window configuration.

#### Processing Logic

1. Slice video into temporal windows.
2. Run action model on windows.
3. Emit start/end action intervals with actor/object links where possible.

#### Outputs

- `vision/actions.json`
- Events: `action_detected` with interval and role bindings

#### Output JSON Example

```json
{
  "schema_version": "1.0",
  "job_id": "uuid",
  "actions": [
    {
      "action_id": "a-19",
      "label": "drop_object",
      "start_sec": 4.05,
      "end_sec": 4.40,
      "actor_track_id": "p-12",
      "object_instance_id": "o-991",
      "confidence": 0.79
    }
  ],
  "model": {
    "name": "slowfast-r50",
    "version": "kinetics-400"
  }
}
```

---

## 4.5 Temporal Engine

The Temporal Engine is the semantic fusion layer that converts independent worker outputs into coherent timeline intelligence.

### Responsibilities

- Normalize all timestamps to a single axis (seconds from video start).
- Resolve overlaps and entity linkage (person-face-object-speech-action).
- Build event graph and flattened timeline.
- Compute derived events (e.g., "speaker likely person p-12").
- Emit conflict/ambiguity markers instead of silent overwrite.

### Inputs

- Normalized worker artifacts from audio/person/face/object/action.
- Entity tables (`persons`, `objects`, identity clusters).

### Outputs

- Unified timeline JSON.
- Fused `events` table records.
- Quality metrics (coverage, ambiguity count, confidence summaries).

### Event Fusion Rules (Core)

1. **Temporal Proximity Window**
   - Use configurable windows for joining events:
     - speech-to-person: ±0.5s to ±1.0s (configurable)
     - action-to-object/person overlap: strict interval intersection
2. **Identity Preference**
   - Face identity match overrides raw track-only identity when confidence above threshold.
3. **Conflict Preservation**
   - Keep competing hypotheses with confidence ranking.
4. **Causality Hints**
   - Optional derived relations:
     - `object_fall` likely after `push` by same actor in short window.

### Timeline JSON Example

```json
{
  "schema_version": "1.0",
  "job_id": "uuid",
  "timeline": [
    {
      "t": 3.20,
      "events": [
        {
          "event_id": "e-1001",
          "type": "speech_segment",
          "person_track_id": "p-12",
          "identity_cluster_id": "id-07",
          "text": "Hello",
          "confidence": 0.90
        }
      ]
    },
    {
      "t": 4.10,
      "events": [
        {
          "event_id": "e-1002",
          "type": "object_detected",
          "object_class": "cup",
          "object_instance_id": "o-34",
          "confidence": 0.87
        }
      ]
    },
    {
      "t": 4.20,
      "events": [
        {
          "event_id": "e-1003",
          "type": "person_present",
          "person_track_id": "p-12",
          "identity_cluster_id": "id-07",
          "confidence": 0.95
        }
      ]
    }
  ]
}
```

### Temporal Engine Diagram (ASCII)

```text
[Audio Events]   [Person Tracks]   [Face IDs]   [Object Events]   [Action Events]
      \               |               |               |                /
       \              |               |               |               /
        +-------------+---------------+---------------+--------------+
                              |
                              v
                   +----------+----------+
                   | Timestamp Normalize |
                   +----------+----------+
                              |
                              v
                   +----------+----------+
                   | Entity Link Resolver|
                   +----------+----------+
                              |
                              v
                   +----------+----------+
                   | Conflict/Ambiguity  |
                   | Annotator           |
                   +----------+----------+
                              |
                              v
                   +----------+----------+
                   | Unified Timeline    |
                   | + Event Graph       |
                   +---------------------+
```

---

## 4.6 Storage System

Three-tier storage strategy:

1. **PostgreSQL**: durable metadata/state/entities/events.
2. **Redis**: transient queueing and runtime state.
3. **File/Object Storage**: media artifacts, frames, embeddings, worker outputs.

## 4.6.1 PostgreSQL Schema (Logical)

### `videos`

- `id` UUID PK
- `external_ref` text nullable
- `file_path` text
- `checksum_sha256` text
- `duration_sec` numeric
- `fps` numeric
- `width` int
- `height` int
- `status` text
- `config_snapshot` jsonb
- `created_at` timestamptz
- `updated_at` timestamptz

### `tasks`

- `id` UUID PK
- `video_id` UUID FK -> videos.id
- `type` text
- `status` text
- `priority` int
- `attempt` int
- `max_attempts` int
- `depends_on` jsonb
- `payload` jsonb
- `worker_id` text nullable
- `queued_at` timestamptz nullable
- `started_at` timestamptz nullable
- `finished_at` timestamptz nullable
- `error_code` text nullable
- `error_message` text nullable
- `created_at` timestamptz
- `updated_at` timestamptz

### `persons`

- `id` UUID PK
- `video_id` UUID FK
- `track_id` text
- `identity_cluster_id` text nullable
- `first_seen_sec` numeric
- `last_seen_sec` numeric
- `face_confidence` numeric nullable
- `attributes` jsonb nullable
- `created_at` timestamptz
- `updated_at` timestamptz

### `objects`

- `id` UUID PK
- `video_id` UUID FK
- `object_instance_id` text
- `class_label` text
- `first_seen_sec` numeric
- `last_seen_sec` numeric
- `confidence_avg` numeric
- `metadata` jsonb nullable
- `created_at` timestamptz
- `updated_at` timestamptz

### `events`

- `id` UUID PK
- `video_id` UUID FK
- `task_id` UUID FK nullable
- `event_type` text
- `start_sec` numeric
- `end_sec` numeric nullable
- `person_id` UUID nullable
- `object_id` UUID nullable
- `payload` jsonb
- `confidence` numeric
- `source_worker` text
- `model_name` text
- `model_version` text
- `created_at` timestamptz

### Optional Supporting Tables (Recommended)

- `model_registry` (model metadata, versions, runtime support)
- `feedback_corrections` (user corrections)
- `analysis_exports` (artifact pointers, schema version)

## 4.6.2 Redis Usage Detail

- Queue lists/streams for each worker.
- In-flight task leases with TTL.
- Job progress cache for dashboards.
- Distributed locks to prevent double-processing.

## 4.6.3 File/Object Storage Layout

```text
storage/
  videos/
    {video_id}/original.mp4
  audio/
    {video_id}/audio.wav
    {video_id}/transcript.json
  frames/
    {video_id}/frame_000001.jpg
  vision/
    {video_id}/person_tracks.json
    {video_id}/faces.json
    {video_id}/objects.json
    {video_id}/actions.json
  embeddings/
    {video_id}/face/
      face_{face_id}.npy
  timeline/
    {video_id}/unified_timeline.json
  logs/
    {video_id}/worker/
```

---

## 4.7 Model Management System

Model management is a dedicated subsystem abstracting lifecycle and runtime choices.

### Responsibilities

- Load/unload models on demand or warm pools.
- Route inference to CPU/GPU based on policy.
- Track model versions and compatibility.
- Provide health checks and memory guards.
- Support fallback models if preferred one unavailable.

### Runtime Policy

- `device_policy = cpu_only | gpu_preferred | gpu_only | auto`
- Worker requests inferencing capability via model manager API.
- Model manager returns active runtime handle or failure reason.

### Versioning Rules

- Every inference output stores:
  - `model_name`
  - `model_version`
  - `runtime_device`
  - `preprocess_version` (if applicable)
- Registry stores approved versions and rollout status:
  - `canary`, `stable`, `deprecated`

### Resource Controls

- Max concurrent inferences per model/device.
- VRAM/RAM thresholds with circuit breaker behavior.
- Idle model unload policies to reclaim memory.

---

## 4.8 Configuration System

A centralized configuration profile defines feature toggles and runtime behavior.

### Configuration Principles

- Immutable snapshot per job (for reproducibility).
- Environment-level defaults + request-level overrides.
- Strict schema validation and versioning.

### Configuration Example (JSON)

```json
{
  "schema_version": "1.0",
  "workers": {
    "audio": true,
    "person": true,
    "face": true,
    "object": true,
    "action": false
  },
  "runtime": {
    "gpu_enabled": false,
    "device_policy": "cpu_only",
    "max_parallel_tasks": 4
  },
  "models": {
    "whisper": "whisper-large-v3",
    "person_detector": "yolov8m",
    "object_detector": "yolov8l-custom",
    "face_embedding": "insightface-arcface",
    "action_model": "slowfast-r50"
  },
  "tracking": {
    "person_tracker": "bytetrack",
    "face_similarity_threshold": 0.42
  },
  "learning": {
    "self_learning_enabled": false,
    "offline_retraining_enabled": true
  }
}
```

---

## 4.9 Feedback and Learning System (Offline)

This subsystem captures human corrections and converts them into retraining data cycles.

### Feedback Inputs

- Correct transcript segment text/timestamps.
- Correct person identity linking.
- Correct object labels.
- Correct event timelines (start/end adjustments).

### Data Capture

- Store corrections in `feedback_corrections`.
- Reference original event/entity IDs.
- Include user confidence/role metadata and timestamp.

### Offline Retraining Pipeline

1. Periodically export validated corrections.
2. Build curated training datasets.
3. Train candidate models offline.
4. Evaluate against benchmark suite.
5. Register promoted model version in `model_registry`.
6. Roll out via canary/staged deployment.

### Critical Constraint

- No real-time weight updates in production inference path.

---

## 5) End-to-End Data Flow

## 5.1 Execution Lifecycle

```text
[1] Upload/Register Video
     -> create videos row
     -> compute metadata/checksum

[2] Orchestrator Plans Tasks
     -> create tasks rows based on config
     -> enqueue root tasks

[3] Workers Execute in Parallel
     -> audio/person/object/face (+action future)
     -> write artifacts + events
     -> update task states

[4] Dependency Completion Check
     -> when required tasks done, enqueue temporal_merge

[5] Temporal Engine Fusion
     -> build unified timeline
     -> persist events + export json

[6] Finalization
     -> mark video status completed/partial/failed
     -> expose artifacts and quality metrics
```

## 5.2 Worker Coordination Topology

```text
audio task ------\
person task ------+--> temporal_merge --> export
face task --------/
object task ------/
action task (future, optional)
```

### Dependency Rules

- `face` may depend on `person` (if face-on-person-crops strategy selected).
- `temporal_merge` depends on all enabled analysis workers.
- `export` depends on `temporal_merge`.

---

## 6) Event Model and Semantics

All detections are transformed into typed events with consistent semantics.

### Event Envelope

```json
{
  "event_id": "uuid",
  "video_id": "uuid",
  "event_type": "speech_segment",
  "start_sec": 3.2,
  "end_sec": 5.1,
  "confidence": 0.93,
  "source_worker": "audio",
  "model": {
    "name": "whisper-large-v3",
    "version": "2026.01",
    "device": "cpu"
  },
  "entities": {
    "person_track_id": "p-12",
    "identity_cluster_id": "id-07",
    "object_instance_id": null
  },
  "payload": {
    "text": "Hello world"
  }
}
```

### Suggested Event Types

- Speech: `speech_segment`
- Person: `person_appeared`, `person_present`, `person_disappeared`
- Face: `face_detected`, `identity_matched`, `identity_uncertain`
- Object: `object_detected`, `object_present`, `object_moved`, `object_dropped`
- Action (future): `action_detected`
- Derived: `speaker_inferred`, `interaction_inferred`

---

## 7) Folder Structure (Implementation Blueprint)

```text
project-root/
  SYSTEM_ARCHITECTURE.md
  configs/
    default.json
    cpu_profile.json
    gpu_profile.json
  orchestrator/
    (job planner, dependency graph, retry policies)
  workers/
    audio/
    person/
    face/
    object/
    action/
    common/
  temporal_engine/
    (event normalizer, linker, timeline builder)
  model_management/
    (registry, loaders, runtime policies)
  storage/
    (postgres adapters, redis adapters, file storage adapters)
  feedback/
    (corrections ingest, dataset export, retraining triggers)
  schemas/
    (json schemas for task/event/artifact/config)
  observability/
    (structured logs, metrics, traces, alerts)
  deployment/
    (container definitions, runtime profiles, env templates)
```

---

## 8) Recommended Model Catalog

The following model choices balance quality, maturity, and integration readiness.

### Audio (ASR)

- **Primary**: Whisper Large v3
- **Fallback (lighter CPU)**: Whisper Medium / Small depending latency budget

### Person Detection

- **Primary**: YOLOv8m (balanced)
- **High Accuracy**: YOLOv8l/x (higher compute)
- **Low Compute**: YOLOv8n/s

### Person Tracking

- **Primary**: ByteTrack
- **Alternative**: DeepSORT

### Face Detection + Embedding

- **Primary stack**: InsightFace (detector + ArcFace embeddings)
- **Alternative stack**: DeepFace with backend embeddings

### Object Detection

- **Primary**: YOLOv8 custom fine-tuned classes
- **Alternative**: General COCO model for baseline

### Action Recognition (Future)

- **Primary candidate**: SlowFast (R50/R101 variants)
- **Alternative**: Video Transformer family (e.g., TimeSformer/VideoMAE style)

### Model Selection Strategy

- Maintain benchmark matrix by:
  - mAP / F1 / WER
  - CPU latency
  - GPU latency
  - memory footprint
  - robustness by domain

---

## 9) Reliability, Observability, and Ops Requirements

## 9.1 Reliability

- At-least-once processing with idempotent task handlers.
- Dead-letter queue for terminal failures.
- Task lease renewal heartbeats for long jobs.
- Checkpointing for long videos to avoid full restart.

## 9.2 Observability

- Structured logging with fields: `job_id`, `task_id`, `worker`, `trace_id`.
- Metrics per worker:
  - throughput
  - avg runtime
  - failure rate
  - queue lag
  - model load times
- Distributed tracing across orchestrator -> queue -> worker -> DB writes.

## 9.3 Alerting

- Queue lag threshold breaches.
- Dead-letter growth spikes.
- Model load failures.
- DB write latency anomalies.

---

## 10) Performance and Scaling Considerations

### CPU-First Baseline

- Frame sampling strategy to control compute cost.
- Dynamic worker concurrency caps.
- Optional model size downgrades for constrained environments.

### GPU Upgrade Path

- Device policy switch in config only.
- GPU-enabled worker pools can be separated by queue name.
- Model manager supports device-aware loading.

### Horizontal Scaling

- Scale workers independently by bottleneck:
  - audio-heavy workloads scale audio workers
  - vision-heavy workloads scale person/object workers
- Redis and PostgreSQL need production tuning for concurrent jobs.

---

## 11) Security and Governance

- Access control for uploaded videos and analysis artifacts.
- Encrypt sensitive artifacts at rest (especially embeddings).
- Store audit logs for analysis requests and feedback edits.
- Data retention policy:
  - raw videos retention configurable
  - derived embeddings retention stricter and controllable

---

## 12) Testing and Validation Strategy

### Test Layers

1. Unit tests for task transitions, event normalization, linkage rules.
2. Integration tests for orchestrator + queue + workers.
3. Regression benchmark suite for model upgrades.
4. End-to-end golden videos with expected timeline outputs.

### Quality Gates

- Minimum coverage thresholds per modality.
- Stability tests on long videos (1+ hour).
- Deterministic output checks under fixed config/model versions.

---

## 13) Rollout Strategy

1. **Phase 1 (MVP CPU)**  
   Audio + Person + Object + Temporal fusion (face optional).

2. **Phase 2 (Identity Enhancement)**  
   Full face identity linking and stronger speaker-person inference.

3. **Phase 3 (GPU Acceleration)**  
   Enable GPU policies and optimize throughput.

4. **Phase 4 (Action Recognition)**  
   Add action worker and expanded event semantics.

5. **Phase 5 (Learning Loop Maturity)**  
   Offline retraining automation and model governance hardening.

---

## 14) Canonical End-to-End Job Example

### Input

- `meeting_room_01.mp4` (duration 00:12:40)
- Config: audio/person/face/object enabled, action disabled, CPU mode.

### Output Narrative

- 00:03.20 person `p-12` speaks (`speech_segment`).
- 00:04.10 object `cup` detected near table.
- 00:04.25 `p-12` identity cluster `id-07` present near cup.
- Timeline retains confidence and source metadata for each event.

### Final Artifacts

- transcript JSON
- person tracks JSON
- face identity JSON
- objects JSON
- unified timeline JSON
- PostgreSQL event/entity rows

---

## 15) Minimum Contracts for Future Extensions

Any new worker must provide:

1. Declared `task_type`.
2. JSON schema for outputs.
3. Event mapping specification.
4. Model metadata and version reporting.
5. Retry/error taxonomy.
6. Compatibility note with Temporal Engine fusion logic.

This keeps the system modular and allows adding/removing models without architecture redesign.

---

## 16) Final Architecture Checklist

- [x] Orchestrator with dependency-aware task control
- [x] Task lifecycle and retry/dead-letter strategy
- [x] Redis queue and transient state design
- [x] Independent workers with explicit input/output contracts
- [x] Temporal fusion engine for unified timeline understanding
- [x] PostgreSQL + Redis + file storage roles defined
- [x] Model management with CPU/GPU policy and versioning
- [x] Centralized configuration with worker/runtime toggles
- [x] Offline feedback learning loop (no real-time updates)
- [x] Production concerns: reliability, observability, scaling, security

This blueprint is sufficient for an engineering team to implement the full system in a controlled, production-oriented manner.
