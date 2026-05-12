from __future__ import annotations

import json
import logging
import signal
import time
from typing import Any

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from db.session import SessionLocal
from services.observability.runtime_trace import RuntimeTrace
from services.orchestration.facade import OrchestrationFacade
from services.scheduler.capability_registry import CapabilityRegistry
from workers.person.worker import process_person_task

logger = logging.getLogger("workers.person_gpu")
STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def _consume_batch(redis_client: Redis, queue_name: str, max_batch: int = 8) -> list[dict[str, Any]]:
    batch: list[dict[str, Any]] = []
    try:
        first = redis_client.brpop(queue_name, timeout=2)
    except RedisConnectionError:
        return batch
    if not first:
        return batch
    _, payload = first
    batch.append(json.loads(payload))
    while len(batch) < max_batch:
        item = redis_client.rpop(queue_name)
        if not item:
            break
        batch.append(json.loads(item))
    return batch


def run_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    registry = CapabilityRegistry(redis_client)
    trace = RuntimeTrace(redis_client=redis_client)
    capability = CapabilityRegistry.make("person", "gpu", ["queue:person:gpu"], batch_capacity=8)

    while not STOP:
        try:
            registry.register(capability)
        except RedisConnectionError:
            logger.info("redis_unavailable_retrying")
            time.sleep(1.0)
            continue
        batch = _consume_batch(redis_client, "queue:person:gpu", max_batch=8)
        if not batch:
            time.sleep(0.2)
            continue
        for item in batch:
            db = SessionLocal()
            orchestration = OrchestrationFacade(redis_client=redis_client)
            lock = orchestration.acquire_execution_lock(item["task_id"], db=db)
            db.close()
            if not lock.acquired:
                continue
            try:
                trace.emit(
                    "worker_started",
                    execution_hash=lock.execution_hash,
                    task_id=item["task_id"],
                    video_id=item["video_id"],
                    component_name="workers.person_gpu",
                )
                process_person_task(item["task_id"])
            finally:
                orchestration.release_execution_lock(lock, task_id=item["task_id"], video_id=item["video_id"])


if __name__ == "__main__":
    run_worker()
