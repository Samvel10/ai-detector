from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from uuid import uuid4

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Task
from db.session import SessionLocal
from services.governance.recovery_authority import RecoveryAuthority
from services.observability.runtime_trace import RuntimeTrace


@dataclass(frozen=True)
class ExecutionLock:
    acquired: bool
    lock_key: str
    token: str
    execution_hash: str


class ExecutionAuthority:
    """
    ONLY component owning execution_hash lifecycle and lock operations.
    """

    _RECONCILED = False
    _RECONCILE_LOCK = threading.Lock()
    _ACTIVE_CACHE: dict[str, float] = {}

    def __init__(self, redis_client: Redis, recovery_authority: RecoveryAuthority | None = None) -> None:
        self.redis = redis_client
        self.trace = RuntimeTrace(redis_client)
        self.recovery = recovery_authority or RecoveryAuthority(redis_client=redis_client)
        self._reconcile_on_startup()

    @staticmethod
    def resolve_execution_hash(task_id: str, db: Session | None = None) -> str:
        if db is None:
            return task_id
        task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
        if task is None:
            return task_id
        return str(task.payload.get("execution_hash", task.id))

    def is_execution_active(self, execution_hash: str) -> bool:
        cache_expiry = self._ACTIVE_CACHE.get(execution_hash, 0.0)
        if cache_expiry > 0.0:
            return True
        try:
            return self.redis.exists(f"execution:active:{execution_hash}") == 1
        except RedisConnectionError:
            return False

    def _reconcile_on_startup(self) -> None:
        with self._RECONCILE_LOCK:
            if self._RECONCILED:
                return
            db = SessionLocal()
            try:
                active, video_last_state = self.recovery.reconstruct_runtime_state(db=db)
                for execution_hash, payload in active.items():
                    expiry = time.time() + 180.0
                    self._ACTIVE_CACHE[execution_hash] = expiry
                    try:
                        self.redis.set(
                            f"execution:active:{execution_hash}",
                            payload.get("task_id", ""),
                            ex=180,
                        )
                    except RedisConnectionError:
                        pass
                for video_id, last_state in video_last_state.items():
                    try:
                        self.redis.hset(f"runtime:last_state:{video_id}", mapping={k: str(v) for k, v in last_state.items()})
                    except RedisConnectionError:
                        pass
            finally:
                db.close()
            try:
                self.cleanup_orphan_executions()
            except RedisConnectionError:
                # Keep startup alive and reconcile when Redis becomes available.
                pass
            self._RECONCILED = True

    def cleanup_orphan_executions(self) -> None:
        now = time.time()
        stale_cache = [key for key, expiry in self._ACTIVE_CACHE.items() if expiry <= now]
        for key in stale_cache:
            self._ACTIVE_CACHE.pop(key, None)
        try:
            for key in self.redis.scan_iter(match="execution:active:*"):
                execution_hash = str(key).split("execution:active:", 1)[-1]
                lock_key = f"execution:lock:{execution_hash}"
                ttl = self.redis.ttl(lock_key)
                if ttl <= 0:
                    self._ACTIVE_CACHE.pop(execution_hash, None)
                    self.redis.delete(key)
                    self.recovery.resolve_orphan_execution(execution_hash=execution_hash, source="ExecutionAuthority.cleanup")
        except RedisConnectionError:
            return

    def acquire(self, task_id: str, video_id: str, db: Session | None = None, ttl_sec: int = 180) -> ExecutionLock:
        self.cleanup_orphan_executions()
        execution_hash = self.resolve_execution_hash(task_id=task_id, db=db)
        token = str(uuid4())
        lock_key = f"execution:lock:{execution_hash}"

        if self.is_execution_active(execution_hash):
            self.recovery.reject_overlap(
                execution_hash=execution_hash,
                task_id=task_id,
                video_id=video_id,
                source="ExecutionAuthority.acquire",
            )
            self.trace.emit(
                "lock_acquired",
                execution_hash=execution_hash,
                task_id=task_id,
                video_id=video_id,
                component_name="ExecutionAuthority",
                extra={"acquired": False, "reason": "active_execution_exists"},
            )
            return ExecutionLock(acquired=False, lock_key=lock_key, token=token, execution_hash=execution_hash)

        try:
            acquired = bool(self.redis.set(lock_key, token, nx=True, ex=ttl_sec))
        except RedisConnectionError:
            acquired = False
        if acquired:
            self._ACTIVE_CACHE[execution_hash] = time.time() + float(ttl_sec)
            try:
                self.redis.set(f"execution:active:{execution_hash}", token, ex=ttl_sec)
            except RedisConnectionError:
                pass
        self.trace.emit(
            "lock_acquired",
            execution_hash=execution_hash,
            task_id=task_id,
            video_id=video_id,
            component_name="ExecutionAuthority",
            extra={"acquired": acquired},
        )
        return ExecutionLock(acquired=acquired, lock_key=lock_key, token=token, execution_hash=execution_hash)

    def release(self, *, lock_key: str, token: str, execution_hash: str, task_id: str, video_id: str) -> None:
        script = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    redis.call("DEL", KEYS[1])
    redis.call("DEL", KEYS[2])
    return 1
end
return 0
"""
        try:
            self.redis.eval(script, 2, lock_key, f"execution:active:{execution_hash}", token)
        except RedisConnectionError:
            pass
        self._ACTIVE_CACHE.pop(execution_hash, None)
        self.trace.emit(
            "execution_completed",
            execution_hash=execution_hash,
            task_id=task_id,
            video_id=video_id,
            component_name="ExecutionAuthority",
        )
