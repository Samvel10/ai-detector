from __future__ import annotations

import hashlib
import json
import logging
import signal
import time

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from core.event_enricher import EventEnricher
from core.event_manager import EventManager
from core.graph_query_engine import GraphQueryEngine
from core.intelligence_graph import IntelligenceGraph
from core.prediction_engine import PredictionEngine
from core.semantic_reasoner import SemanticReasoner
from db.models import Video
from db.session import SessionLocal, init_db
from services.observability.runtime_trace import RuntimeTrace
from services.realtime.event_streams import RealtimeStreamPublisher

logger = logging.getLogger("realtime.bridge")
STOP = False


def _request_stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def _hash_payload(data: object) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_bridge(poll_interval_sec: float = 2.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    init_db()

    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    publisher = RealtimeStreamPublisher(redis_client=redis_client)
    trace = RuntimeTrace(redis_client=redis_client)

    while not STOP:
        db = SessionLocal()
        try:
            event_manager = EventManager(db=db)
            enricher = EventEnricher()
            graph = IntelligenceGraph()
            graph_query = GraphQueryEngine()
            semantic = SemanticReasoner(event_manager=event_manager, graph_query_engine=graph_query)
            prediction = PredictionEngine(graph_query_engine=graph_query, semantic_reasoner=semantic)

            videos = db.execute(select(Video.id)).all()
            for (video_id,) in videos:
                raw_events = event_manager.query_events(video_id)
                execution_hash = f"video:{video_id}:bridge"
                trace.emit(
                    "event_persisted",
                    execution_hash=execution_hash,
                    task_id="bridge",
                    video_id=video_id,
                    component_name="realtime.bridge",
                    extra={"event_count": len(raw_events)},
                )
                enriched = enricher.enrich(job_id=video_id, raw_events=raw_events)
                state = graph.build_or_update(job_id=video_id, enriched_events=enriched)
                trace.emit(
                    "graph_updated",
                    execution_hash=execution_hash,
                    task_id="bridge",
                    video_id=video_id,
                    component_name="realtime.bridge",
                    extra={"graph_version": state.graph_version},
                )

                timeline_payload = {"events": [event.model_dump() for event in raw_events]}
                tracking_payload = {
                    "events": [event for event in enriched if event.get("event_type") in {"person_detected", "person_track_start", "person_track_end"}]
                }
                graph_payload = {
                    "graph_version": state.graph_version,
                    "node_count": len(state.nodes),
                    "edge_count": len(state.edges),
                }
                semantic_payload = {
                    "scene": semantic.build_scene_understanding(video_id),
                    "interactions": semantic.build_interactions(video_id),
                    "timeline": semantic.build_narrative_timeline(video_id),
                }
                trace.emit(
                    "semantic_updated",
                    execution_hash=execution_hash,
                    task_id="bridge",
                    video_id=video_id,
                    component_name="realtime.bridge",
                )
                prediction_payload = {
                    "actions": prediction.predict_actions(video_id),
                    "interactions": prediction.predict_interactions(video_id),
                    "scene": prediction.predict_scene_evolution(video_id),
                }
                trace.emit(
                    "prediction_updated",
                    execution_hash=execution_hash,
                    task_id="bridge",
                    video_id=video_id,
                    component_name="realtime.bridge",
                )

                publisher.publish(video_id, "timeline", _hash_payload(timeline_payload), timeline_payload)
                publisher.publish(video_id, "tracking", _hash_payload(tracking_payload), tracking_payload)
                publisher.publish(video_id, "graph", _hash_payload(graph_payload), graph_payload)
                publisher.publish(video_id, "semantic", _hash_payload(semantic_payload), semantic_payload)
                publisher.publish(video_id, "prediction", _hash_payload(prediction_payload), prediction_payload)

            # Single-source emission for system alerts (from watchdog/retry/self-heal)
            alert_item = redis_client.rpop("queue:system_alerts")
            if alert_item:
                alert = json.loads(alert_item)
                publisher.publish("system", "system", _hash_payload(alert), alert)

        except RedisConnectionError:
            logger.info("realtime_bridge_redis_unavailable_retrying")
        except Exception:
            logger.exception("realtime_bridge_iteration_failed")
        finally:
            db.close()

        time.sleep(poll_interval_sec)


if __name__ == "__main__":
    run_bridge()
