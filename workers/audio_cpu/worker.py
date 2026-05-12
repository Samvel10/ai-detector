from __future__ import annotations

import json
import logging
import signal
import time

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from db.session import SessionLocal
from services.observability.runtime_trace import RuntimeTrace
from services.orchestration.facade import OrchestrationFacade
from services.scheduler.capability_registry import CapabilityRegistry
from workers.audio.worker import process_audio_task

logger = logging.getLogger("workers.audio_cpu")
STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def run_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    registry = CapabilityRegistry(redis_client)
    trace = RuntimeTrace(redis_client=redis_client)
    capability = CapabilityRegistry.make("audio", "cpu", ["queue:audio:cpu"], batch_capacity=1)

    while not STOP:
        try:
            registry.register(capability)
            message = redis_client.brpop("queue:audio:cpu", timeout=2)
        except RedisConnectionError:
            logger.info("redis_unavailable_retrying")
            time.sleep(1.0)
            continue
        if not message:
            continue
        _, payload = message
        body = json.loads(payload)
        db = SessionLocal()
        orchestration = OrchestrationFacade(redis_client=redis_client)
        lock = orchestration.acquire_execution_lock(body["task_id"], db=db)
        db.close()
        if not lock.acquired:
            continue
        try:
            trace.emit(
                "worker_started",
                execution_hash=lock.execution_hash,
                task_id=body["task_id"],
                video_id=body["video_id"],
                component_name="workers.audio_cpu",
            )
            process_audio_task(body["task_id"])
        finally:
            orchestration.release_execution_lock(lock, task_id=body["task_id"], video_id=body["video_id"])
        time.sleep(0.01)


if __name__ == "__main__":
    run_worker()
