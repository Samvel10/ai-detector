from __future__ import annotations

import json
import os

from redis import Redis
from services.governance.recovery_authority import RecoveryAuthority
from services.observability.runtime_trace import RuntimeTrace
from services.orchestration.execution_authority import ExecutionAuthority


class SchedulingDecisionEngine:
    """
    Stateless queue-routing authority:
    - target queue selection
    - source queue draining/rerouting
    """

    def __init__(
        self,
        redis_client: Redis,
        execution_authority: ExecutionAuthority | None = None,
        recovery_authority: RecoveryAuthority | None = None,
    ) -> None:
        self.redis = redis_client
        self.execution_authority = execution_authority
        self.recovery = recovery_authority or RecoveryAuthority(redis_client=redis_client)
        self.trace = RuntimeTrace(redis_client=redis_client)

    @staticmethod
    def _debug_assert_no_overlap(operation: str) -> None:
        if os.getenv("ORCHESTRATION_DEBUG", "0") == "1":
            forbidden = {"retry", "lock", "execution"}
            if any(word in operation.lower() for word in forbidden):
                raise RuntimeError("SchedulingDecisionEngine boundary violation")

    @staticmethod
    def base_queue(task_type: str) -> str | None:
        if task_type == "preprocessing":
            return "queue:preprocessing"
        if task_type == "audio":
            return "queue:audio"
        if task_type == "person":
            return "queue:person"
        return None

    def select_execution_queue(self, task_type: str) -> str | None:
        self._debug_assert_no_overlap("route_decision")
        if task_type not in {"audio", "person"}:
            return self.base_queue(task_type)

        gpu_queue = f"queue:{task_type}:gpu"
        cpu_queue = f"queue:{task_type}:cpu"

        has_gpu_worker = False
        for key in self.redis.smembers("worker:capability:index"):
            payload = self.redis.get(key)
            if not payload:
                continue
            data = json.loads(payload)
            if data.get("worker_type") == task_type and data.get("device_type") == "gpu":
                has_gpu_worker = True
                break
        return gpu_queue if has_gpu_worker else cpu_queue

    def enqueue(
        self,
        task_id: str,
        video_id: str,
        task_type: str,
        queue_name: str | None = None,
        execution_hash: str | None = None,
    ) -> bool:
        self._debug_assert_no_overlap("queue_selection")
        queue = queue_name or self.select_execution_queue(task_type)
        if queue is None:
            return False
        resolved_execution_hash = str(execution_hash or task_id)
        if self.execution_authority and self.execution_authority.is_execution_active(resolved_execution_hash):
            self.recovery.reject_overlap(
                execution_hash=resolved_execution_hash,
                task_id=task_id,
                video_id=video_id,
                source="SchedulingDecisionEngine.enqueue",
            )
            return False
        self.redis.lpush(
            queue,
            json.dumps(
                {
                    "task_id": task_id,
                    "video_id": video_id,
                    "task_type": task_type,
                    "execution_hash": resolved_execution_hash,
                }
            ),
        )
        self.trace.emit(
            "route_decision",
            execution_hash=resolved_execution_hash,
            task_id=task_id,
            video_id=video_id,
            component_name="SchedulingDecisionEngine",
            extra={"target_queue": queue, "task_type": task_type},
        )
        return True

    def route_from_sources(self, source_queues: list[str]) -> None:
        self._debug_assert_no_overlap("source_routing")
        for source in source_queues:
            item = self.redis.rpop(source)
            if not item:
                continue
            body = json.loads(item)
            execution_hash = body.get("execution_hash")
            if execution_hash and self.execution_authority and self.execution_authority.is_execution_active(str(execution_hash)):
                self.recovery.reject_overlap(
                    execution_hash=str(execution_hash),
                    task_id=str(body.get("task_id", "")),
                    video_id=str(body.get("video_id", "")),
                    source="SchedulingDecisionEngine.route_from_sources",
                )
                continue
            target = self.select_execution_queue(str(body.get("task_type", "")))
            if target is None:
                self.redis.lpush(source, item)
                continue
            body.setdefault("execution_hash", str(body.get("task_id", "")))
            self.redis.lpush(target, json.dumps(body))
