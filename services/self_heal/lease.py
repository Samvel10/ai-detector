from __future__ import annotations

import uuid

from redis import Redis


class TaskLease:
    def __init__(self, redis_client: Redis, task_id: str, ttl_sec: int = 120) -> None:
        self.redis = redis_client
        self.task_id = task_id
        self.ttl_sec = ttl_sec
        self.token = str(uuid.uuid4())
        self.key = f"lease:task:{task_id}"

    def acquire(self) -> bool:
        return bool(self.redis.set(self.key, self.token, nx=True, ex=self.ttl_sec))

    def renew(self) -> None:
        script = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("EXPIRE", KEYS[1], ARGV[2])
end
return 0
"""
        self.redis.eval(script, 1, self.key, self.token, self.ttl_sec)

    def release(self) -> None:
        script = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""
        self.redis.eval(script, 1, self.key, self.token)
