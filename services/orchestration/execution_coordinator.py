from __future__ import annotations

import os

from redis import Redis
from sqlalchemy.orm import Session

from services.governance.recovery_authority import RecoveryAuthority
from services.orchestration.execution_authority import ExecutionAuthority, ExecutionLock


class ExecutionCoordinator:
    """
    Stateless execution authority:
    - execution_hash resolution
    - lock acquisition/release
    """

    def __init__(self, redis_client: Redis, recovery_authority: RecoveryAuthority | None = None) -> None:
        self.authority = ExecutionAuthority(redis_client=redis_client, recovery_authority=recovery_authority)

    @staticmethod
    def _debug_guard() -> None:
        if os.getenv("ORCHESTRATION_DEBUG", "0") == "1":
            # Coordinator owns execution flow only.
            return

    def acquire(self, task_id: str, video_id: str, db: Session | None = None, ttl_sec: int = 180) -> ExecutionLock:
        self._debug_guard()
        return self.authority.acquire(task_id=task_id, video_id=video_id, db=db, ttl_sec=ttl_sec)

    def release(self, lock: ExecutionLock, task_id: str, video_id: str) -> None:
        self._debug_guard()
        self.authority.release(
            lock_key=lock.lock_key,
            token=lock.token,
            execution_hash=lock.execution_hash,
            task_id=task_id,
            video_id=video_id,
        )

    def is_execution_active(self, execution_hash: str) -> bool:
        self._debug_guard()
        return self.authority.is_execution_active(execution_hash)
