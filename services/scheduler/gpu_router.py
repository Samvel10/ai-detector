from __future__ import annotations

import logging
import signal
import time

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from services.orchestration.facade import OrchestrationFacade

logger = logging.getLogger("scheduler.gpu_router")
STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def run_router() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    orchestration = OrchestrationFacade(redis_client=redis_client)

    source_queues = ["queue:audio", "queue:person"]
    while not STOP:
        try:
            orchestration.route_from_source_queues(source_queues)
            time.sleep(0.25)
        except RedisConnectionError:
            logger.info("redis_unavailable_retrying")
            time.sleep(1.0)


if __name__ == "__main__":
    run_router()
