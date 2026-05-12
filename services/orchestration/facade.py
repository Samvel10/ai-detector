from __future__ import annotations

import json

from redis import Redis
from sqlalchemy.orm import Session

from db.models import Task
from services.governance.recovery_authority import RecoveryAuthority
from services.observability.runtime_trace import RuntimeTrace
from services.orchestration.execution_authority import ExecutionLock
from services.orchestration.execution_coordinator import ExecutionCoordinator
from services.orchestration.retry_policy_engine import RetryPolicyEngine
from services.orchestration.scheduling_decision_engine import SchedulingDecisionEngine


class OrchestrationFacade:
    """
    Thin delegation-only facade.
    """

    def __init__(self, redis_client: Redis) -> None:
        self.recovery = RecoveryAuthority(redis_client=redis_client)
        self.execution = ExecutionCoordinator(redis_client=redis_client, recovery_authority=self.recovery)
        self.scheduler = SchedulingDecisionEngine(
            redis_client=redis_client,
            execution_authority=self.execution.authority,
            recovery_authority=self.recovery,
        )
        self.retry = RetryPolicyEngine()
        self.redis = redis_client
        self.trace = RuntimeTrace(redis_client=redis_client)

    def acquire_execution_lock(self, task_id: str, db: Session | None = None, ttl_sec: int = 180) -> ExecutionLock:
        video_id = ""
        if db is not None:
            task = db.get(Task, task_id)
            if task is not None:
                video_id = task.video_id
        lock = self.execution.acquire(task_id=task_id, video_id=video_id, db=db, ttl_sec=ttl_sec)
        self.trace.emit(
            "task_received",
            execution_hash=lock.execution_hash,
            task_id=task_id,
            video_id=video_id,
            component_name="OrchestrationFacade",
            extra={"lock_acquired": lock.acquired},
        )
        return lock

    def release_execution_lock(self, lock: ExecutionLock, task_id: str, video_id: str) -> None:
        self.execution.release(lock=lock, task_id=task_id, video_id=video_id)

    def select_execution_queue(self, task_type: str) -> str | None:
        return self.scheduler.select_execution_queue(task_type)

    def enqueue_task_message(
        self,
        task_id: str,
        video_id: str,
        task_type: str,
        queue_name: str | None = None,
        execution_hash: str | None = None,
    ) -> bool:
        return self.scheduler.enqueue(
            task_id=task_id,
            video_id=video_id,
            task_type=task_type,
            queue_name=queue_name,
            execution_hash=execution_hash,
        )

    def route_from_source_queues(self, source_queues: list[str]) -> None:
        self.scheduler.route_from_sources(source_queues)

    def schedule_retry(self, task: Task) -> bool:
        execution_hash = str(task.payload.get("execution_hash", task.id))
        decision = self.retry.decision(task, execution_active=self.execution.is_execution_active(execution_hash))
        if decision == "blocked_active_execution":
            self.recovery.reject_overlap(
                execution_hash=execution_hash,
                task_id=task.id,
                video_id=task.video_id,
                source="OrchestrationFacade.schedule_retry",
            )
            return False
        if decision == "non_retryable" or decision == "defer":
            return False
        if decision == "dead_letter":
            self.redis.lpush("queue:dead_letter", json.dumps({"task_id": task.id, "video_id": task.video_id}))
            self.trace.emit(
                "retry_scheduled",
                execution_hash=execution_hash,
                task_id=task.id,
                video_id=task.video_id,
                component_name="OrchestrationFacade",
                extra={"action": "dead_letter"},
            )
            return False
        self.retry.apply_retry_transition(task)
        queue_name = self.select_execution_queue(task.type)
        if queue_name is None:
            return False
        if not self.enqueue_task_message(
            task.id,
            task.video_id,
            task.type,
            queue_name=queue_name,
            execution_hash=execution_hash,
        ):
            return False
        self.trace.emit(
            "retry_scheduled",
            execution_hash=execution_hash,
            task_id=task.id,
            video_id=task.video_id,
            component_name="OrchestrationFacade",
            extra={"action": "enqueue", "queue": queue_name},
        )
        return True

    def publish_system_alert(self, alert_type: str, payload: dict) -> None:
        self.redis.lpush("queue:system_alerts", json.dumps({"alert_type": alert_type, "payload": payload}))
