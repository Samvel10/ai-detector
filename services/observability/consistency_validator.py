from __future__ import annotations

import logging
import os
import signal
import time

from redis import Redis
from sqlalchemy import select

from core.event_enricher import EventEnricher
from core.event_manager import EventManager
from core.graph_query_engine import GraphQueryEngine
from core.prediction_engine import PredictionEngine
from core.semantic_reasoner import SemanticReasoner
from db.models import Video
from db.session import SessionLocal, init_db
from services.governance.recovery_authority import RecoveryAuthority
from services.observability.runtime_trace import RuntimeTrace

logger = logging.getLogger("observability.consistency_validator")
STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def validate_video(video_id: str, redis_client: Redis) -> list[str]:
    db = SessionLocal()
    violations: list[str] = []
    try:
        event_manager = EventManager(db=db)
        enricher = EventEnricher()
        graph_query = GraphQueryEngine()
        semantic = SemanticReasoner(event_manager=event_manager, graph_query_engine=graph_query)
        prediction = PredictionEngine(graph_query_engine=graph_query, semantic_reasoner=semantic)

        raw_events = event_manager.query_events(video_id)
        if not raw_events:
            violations.append("missing_raw_events")
            return violations

        timestamps = [float(event.timestamp_sec) for event in raw_events]
        if timestamps != sorted(timestamps):
            violations.append("non_monotonic_raw_timestamps")

        enriched_events = enricher.enrich(job_id=video_id, raw_events=raw_events)
        if not enriched_events:
            violations.append("missing_enriched_events")

        graph_state = graph_query._load(video_id)
        if graph_state is None:
            violations.append("missing_graph_snapshot")

        scene = semantic.build_scene_understanding(video_id)
        interactions = semantic.build_interactions(video_id)
        timeline = semantic.build_narrative_timeline(video_id)
        if not scene:
            violations.append("missing_semantic_scene")
        if timeline is None:
            violations.append("missing_semantic_timeline")

        prediction_scene = prediction.predict_scene_evolution(video_id)
        if not prediction_scene:
            violations.append("missing_prediction_scene")

        if graph_state is not None:
            node_ids = set(graph_state.nodes.keys())
            for enriched in enriched_events:
                payload = dict(enriched.get("payload", {}))
                entity_id = payload.get("entity_id") or payload.get("candidate_speaker_entity_id")
                if entity_id:
                    graph_entity_node = f"{video_id}:PersonEntity:{entity_id}"
                    if graph_entity_node not in node_ids:
                        violations.append(f"missing_graph_entity_node:{entity_id}")
                        break

        _ = interactions
    finally:
        db.close()
    return sorted(set(violations))


def run_consistency_validator(poll_interval_sec: float = 10.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    init_db()
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    trace = RuntimeTrace(redis_client=redis_client)
    recovery = RecoveryAuthority(redis_client=redis_client)
    auto_recovery_enabled = os.getenv("CONSISTENCY_AUTO_RECOVERY", "1") == "1"
    boot_reconciled = False

    while not STOP:
        db = SessionLocal()
        try:
            videos = db.execute(select(Video)).scalars().all()
            if not boot_reconciled:
                for key in redis_client.scan_iter(match="runtime:last_state:*"):
                    video_id = str(key).split("runtime:last_state:", 1)[-1]
                    if any(video.id == video_id for video in videos):
                        _ = validate_video(video_id, redis_client=redis_client)
                boot_reconciled = True
            for video in videos:
                violations = validate_video(video.id, redis_client=redis_client)
                if not violations:
                    continue
                decision = recovery.resolve_consistency_violations(
                    video_id=video.id,
                    violations=violations,
                    auto_recovery_enabled=auto_recovery_enabled,
                )
                severity = str(decision.get("severity", "warning"))
                metadata = dict(video.metadata_json or {})
                metadata["degraded"] = severity in {"degraded", "critical"}
                metadata["degraded_reason"] = violations
                metadata["degraded_severity"] = severity
                video.metadata_json = metadata
                recovery.write_checkpoint(
                    video.id,
                    {
                        "degraded": metadata["degraded"],
                        "degraded_reason": violations,
                        "degraded_severity": severity,
                    },
                )
                trace.emit(
                    "event_persisted",
                    execution_hash=f"video:{video.id}:consistency",
                    task_id="consistency-validator",
                    video_id=video.id,
                    component_name="consistency_validator",
                    extra={
                        "violations": violations,
                        "severity": severity,
                        "recovery_triggered": bool(decision.get("replay_triggered", False)),
                    },
                )
            db.commit()
        except Exception:
            logger.exception("consistency_validator_iteration_failed")
            db.rollback()
        finally:
            db.close()
        time.sleep(poll_interval_sec)


if __name__ == "__main__":
    run_consistency_validator()
