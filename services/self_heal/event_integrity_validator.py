from __future__ import annotations

import json
import signal
import time

from redis import Redis
from sqlalchemy import select

from core.event_enricher import EventEnricher
from core.event_manager import EventManager
from core.intelligence_graph import IntelligenceGraph
from db.models import Video
from db.session import SessionLocal, init_db

STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def run_validator() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    init_db()
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    while not STOP:
        db = SessionLocal()
        try:
            event_manager = EventManager(db=db)
            enricher = EventEnricher()
            graph = IntelligenceGraph()
            degraded: list[dict] = []
            for (video_id,) in db.execute(select(Video.id)).all():
                events = event_manager.query_events(video_id)
                if any(events[idx].timestamp_sec > events[idx + 1].timestamp_sec for idx in range(len(events) - 1)):
                    degraded.append({"video_id": video_id, "reason": "timestamp_order_violation"})
                    continue
                enriched = enricher.enrich(job_id=video_id, raw_events=events)
                computed_version = graph.compute_graph_version(graph.canonical_order_events(enriched))
                snapshot = graph.load_snapshot(video_id)
                if snapshot is None or snapshot.graph_version != computed_version:
                    degraded.append({"video_id": video_id, "reason": "graph_version_mismatch"})
            redis_client.set("validator:degraded", json.dumps(degraded, ensure_ascii=True), ex=30)
        finally:
            db.close()
        time.sleep(10)


if __name__ == "__main__":
    run_validator()
