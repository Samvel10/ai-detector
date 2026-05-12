from __future__ import annotations

import json
import signal
import time
import uuid

from redis import Redis

STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def run_heartbeat(service_name: str, interval_sec: float = 5.0) -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    instance_id = str(uuid.uuid4())
    key = f"heartbeat:{service_name}:{instance_id}"
    while not STOP:
        payload = {"service": service_name, "instance_id": instance_id, "updated_at": time.time()}
        redis_client.set(key, json.dumps(payload, ensure_ascii=True), ex=15)
        time.sleep(interval_sec)


if __name__ == "__main__":
    run_heartbeat("generic")
