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
from services.governance.recovery_authority import RecoveryAuthority

STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def run_reprocessor() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    init_db()
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    recovery = RecoveryAuthority(redis_client=redis_client)
    while not STOP:
        try:
            replay_item = redis_client.lpop("queue:deterministic_replay")
            replay_targets = []
            if replay_item:
                try:
                    replay_targets.append(json.loads(replay_item))
                except Exception:
                    replay_targets = []
            raw = redis_client.get("validator:degraded")
            if raw:
                degraded = json.loads(raw)
                replay_targets.extend(degraded)
            if replay_targets:
                db = SessionLocal()
                try:
                    event_manager = EventManager(db=db)
                    enricher = EventEnricher()
                    graph = IntelligenceGraph()
                    valid_video_ids = {video_id for (video_id,) in db.execute(select(Video.id)).all()}
                    for item in replay_targets:
                        video_id = item.get("video_id")
                        if video_id not in valid_video_ids:
                            continue
                        replay_from_ts = item.get("replay_from_ts")
                        if replay_from_ts is None:
                            checkpoint_start = recovery.replay_window_start(video_id)
                            replay_from_ts = checkpoint_start if checkpoint_start is not None else None
                        if replay_from_ts is None:
                            events = event_manager.query_events(video_id)
                        else:
                            events = event_manager.query_events_by_time_range(video_id, float(replay_from_ts), 10**9)
                        enriched = enricher.enrich(job_id=video_id, raw_events=events)
                        graph.build_or_update(video_id, enriched)
                        if events:
                            recovery.mark_replay_completed(
                                video_id=video_id,
                                last_replayed_event_ts=max(float(event.timestamp_sec) for event in events),
                            )
                finally:
                    db.close()
        except Exception:
            pass
        time.sleep(10)


if __name__ == "__main__":
    run_reprocessor()
