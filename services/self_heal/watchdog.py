from __future__ import annotations

import json
import signal
import time

from redis import Redis
from services.governance.recovery_authority import RecoveryAuthority

STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def run_watchdog() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    recovery = RecoveryAuthority(redis_client=redis_client)
    observed_queues = [
        "queue:preprocessing",
        "queue:audio",
        "queue:person",
        "queue:audio:cpu",
        "queue:audio:gpu",
        "queue:person:cpu",
        "queue:person:gpu",
        "queue:dead_letter",
    ]
    while not STOP:
        try:
            snapshot = {queue: redis_client.llen(queue) for queue in observed_queues}
            redis_client.set("watchdog:queue_snapshot", json.dumps(snapshot, ensure_ascii=True), ex=30)
            if snapshot.get("queue:dead_letter", 0) > 100:
                recovery.report_system_signal("dead_letter_growth", {"snapshot": snapshot})
        except Exception:
            # Keep watchdog process alive during transient redis outages.
            pass
        time.sleep(5)


if __name__ == "__main__":
    run_watchdog()
