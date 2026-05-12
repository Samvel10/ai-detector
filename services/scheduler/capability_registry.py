from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass

from redis import Redis


@dataclass
class WorkerCapability:
    worker_id: str
    worker_type: str
    device_type: str
    queues: list[str]
    batch_capacity: int
    updated_at: float


class CapabilityRegistry:
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def register(self, capability: WorkerCapability, ttl_sec: int = 20) -> None:
        key = f"worker:capability:{capability.worker_id}"
        self.redis.set(key, json.dumps(asdict(capability), ensure_ascii=True), ex=ttl_sec)
        self.redis.sadd("worker:capability:index", key)

    def list_capabilities(self) -> list[WorkerCapability]:
        capabilities: list[WorkerCapability] = []
        for key in self.redis.smembers("worker:capability:index"):
            payload = self.redis.get(key)
            if not payload:
                self.redis.srem("worker:capability:index", key)
                continue
            data = json.loads(payload)
            capabilities.append(WorkerCapability(**data))
        return capabilities

    @staticmethod
    def make(worker_type: str, device_type: str, queues: list[str], batch_capacity: int) -> WorkerCapability:
        return WorkerCapability(
            worker_id=str(uuid.uuid4()),
            worker_type=worker_type,
            device_type=device_type,
            queues=queues,
            batch_capacity=batch_capacity,
            updated_at=time.time(),
        )
