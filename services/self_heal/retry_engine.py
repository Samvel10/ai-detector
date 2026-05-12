from __future__ import annotations

import signal
import time

from redis import Redis
from sqlalchemy import select

from db.models import Task, TaskStatus
from db.session import SessionLocal, init_db
from services.orchestration.facade import OrchestrationFacade

STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def run_retry_engine() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    init_db()
    redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)

    while not STOP:
        db = SessionLocal()
        try:
            orchestration = OrchestrationFacade(redis_client=redis_client)
            failed_tasks = db.execute(select(Task).where(Task.status == TaskStatus.failed)).scalars().all()
            for task in failed_tasks:
                orchestration.schedule_retry(task)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        time.sleep(2)


if __name__ == "__main__":
    run_retry_engine()
