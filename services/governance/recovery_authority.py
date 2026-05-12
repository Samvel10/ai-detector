from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Task, Video


class RecoveryAuthority:
    """
    Single authority for all recovery decisions and resolution actions.

    Truth hierarchy:
    1) runtime_trace.jsonl (immutable history)
    2) PostgreSQL state (durable snapshot)
    3) Redis live state (ephemeral cache)
    """

    def __init__(self, redis_client: Redis, checkpoint_dir: str = "storage/recovery_checkpoints") -> None:
        self.redis = redis_client
        self.trace_path = Path("storage/runtime_trace.jsonl")
        self.checkpoint_root = Path(checkpoint_dir)

    def _emit_alert(self, alert_type: str, payload: dict[str, Any]) -> None:
        self.redis.lpush("queue:system_alerts", json.dumps({"alert_type": alert_type, "payload": payload}))

    def report_system_signal(self, signal_type: str, payload: dict[str, Any]) -> None:
        self._emit_alert(signal_type, payload)

    def reject_overlap(self, *, execution_hash: str, task_id: str, video_id: str, source: str) -> bool:
        self._emit_alert(
            "execution_overlap_rejected",
            {
                "execution_hash": execution_hash,
                "task_id": task_id,
                "video_id": video_id,
                "source": source,
            },
        )
        return False

    def classify_consistency_severity(self, violations: list[str]) -> str:
        critical_markers = {"missing_raw_events", "missing_graph_snapshot", "missing_prediction_scene"}
        degraded_markers = {"missing_enriched_events", "non_monotonic_raw_timestamps", "missing_semantic_scene"}
        if any(any(marker in violation for marker in critical_markers) for violation in violations):
            return "critical"
        if any(any(marker in violation for marker in degraded_markers) for violation in violations):
            return "degraded"
        return "warning"

    def resolve_consistency_violations(self, video_id: str, violations: list[str], auto_recovery_enabled: bool) -> dict[str, Any]:
        severity = self.classify_consistency_severity(violations)
        self._emit_alert(
            "consistency_violation",
            {"video_id": video_id, "violations": violations, "severity": severity},
        )
        replay_triggered = False
        if auto_recovery_enabled and severity == "critical":
            replay_triggered = True
            checkpoint = self.load_checkpoint(video_id) or {}
            replay_from_ts = float(checkpoint.get("state", {}).get("last_replayed_event_ts", 0.0))
            replay_entry = {
                "video_id": video_id,
                "reason": "critical_consistency_violation",
                "triggered_at": time.time(),
                "replay_from_ts": replay_from_ts,
            }
            self.redis.rpush("queue:deterministic_replay", json.dumps(replay_entry))
            degraded_raw = self.redis.get("validator:degraded")
            degraded = json.loads(degraded_raw) if degraded_raw else []
            degraded = [item for item in degraded if item.get("video_id") != video_id]
            degraded.append(replay_entry)
            self.redis.set("validator:degraded", json.dumps(degraded))
            self.write_checkpoint(
                video_id,
                {
                    "last_recovery_reason": "critical_consistency_violation",
                    "last_replay_start_sec": replay_from_ts,
                },
            )
        return {"severity": severity, "replay_triggered": replay_triggered}

    def resolve_orphan_execution(self, execution_hash: str, source: str) -> None:
        self._emit_alert(
            "orphan_execution_cleanup",
            {"execution_hash": execution_hash, "source": source},
        )

    def reconstruct_runtime_state(self, db: Session) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        active: dict[str, dict[str, Any]] = {}
        video_last_state: dict[str, dict[str, Any]] = {}
        if not self.trace_path.exists():
            return active, video_last_state
        with self.trace_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                execution_hash = str(payload.get("execution_hash", ""))
                event_name = str(payload.get("trace_event", ""))
                if not execution_hash:
                    continue
                task_id = str(payload.get("task_id", ""))
                video_id = str(payload.get("video_id", ""))
                if video_id:
                    video_last_state[video_id] = {
                        "trace_event": event_name,
                        "execution_hash": execution_hash,
                        "task_id": task_id,
                        "timestamp": float(payload.get("timestamp", 0.0)),
                    }
                if event_name in {"lock_acquired", "worker_started"} and payload.get("extra", {}).get("acquired", True):
                    active[execution_hash] = payload
                if event_name == "execution_completed":
                    active.pop(execution_hash, None)

        # Truth hierarchy enforcement: validate against PostgreSQL before touching Redis.
        valid_task_ids = set(db.execute(select(Task.id)).scalars().all())
        valid_video_ids = set(db.execute(select(Video.id)).scalars().all())
        active = {
            execution_hash: payload
            for execution_hash, payload in active.items()
            if str(payload.get("task_id", "")) in valid_task_ids and str(payload.get("video_id", "")) in valid_video_ids
        }
        video_last_state = {
            video_id: payload for video_id, payload in video_last_state.items() if video_id in valid_video_ids
        }
        return active, video_last_state

    def write_checkpoint(self, video_id: str, state: dict[str, Any]) -> None:
        self.checkpoint_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "video_id": video_id,
            "checkpoint_ts": time.time(),
            "state": state,
        }
        with (self.checkpoint_root / f"{video_id}.json").open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, sort_keys=True)

    def load_checkpoint(self, video_id: str) -> dict[str, Any] | None:
        path = self.checkpoint_root / f"{video_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def replay_window_start(self, video_id: str) -> float | None:
        checkpoint = self.load_checkpoint(video_id)
        if not checkpoint:
            return None
        value = checkpoint.get("state", {}).get("last_replayed_event_ts")
        if value is None:
            return None
        return float(value)

    def mark_replay_completed(self, video_id: str, last_replayed_event_ts: float) -> None:
        checkpoint = self.load_checkpoint(video_id) or {}
        state = dict(checkpoint.get("state", {}))
        state["last_replayed_event_ts"] = float(last_replayed_event_ts)
        state["last_replay_completed_at"] = time.time()
        self.write_checkpoint(video_id, state)
