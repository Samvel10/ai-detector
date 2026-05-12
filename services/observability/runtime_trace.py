from __future__ import annotations

import atexit
import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from redis import Redis


class RuntimeTrace:
    """
    Deterministic append-only runtime trace logger.
    """

    _INIT_LOCK = threading.Lock()
    _STARTED = False
    _STOP = False
    _BUFFER: deque[str] = deque()
    _BUFFER_LOCK = threading.Lock()
    _FLUSH_THREAD: threading.Thread | None = None
    _MAX_BUFFER = 5000
    _FLUSH_INTERVAL_SEC = 0.5
    _BATCH_SIZE = 200
    _TRACE_PATH: Path | None = None
    _SPILL_PATH: Path | None = None
    _REDIS_CLIENTS: list[Redis] = []

    def __init__(self, redis_client: Redis | None = None, trace_file: str = "storage/runtime_trace.jsonl") -> None:
        self.redis = redis_client
        self.trace_path = Path(trace_file)
        self._start_once(self.trace_path, redis_client)

    @classmethod
    def _start_once(cls, trace_path: Path, redis_client: Redis | None) -> None:
        with cls._INIT_LOCK:
            if redis_client is not None:
                cls._REDIS_CLIENTS.append(redis_client)
            if cls._STARTED:
                return
            cls._TRACE_PATH = trace_path
            cls._SPILL_PATH = trace_path.with_suffix(".spill.jsonl")
            cls._TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
            cls._STOP = False
            cls._FLUSH_THREAD = threading.Thread(target=cls._flush_loop, name="runtime-trace-flush", daemon=True)
            cls._FLUSH_THREAD.start()
            cls._STARTED = True
            atexit.register(cls.shutdown)

    @classmethod
    def _flush_loop(cls) -> None:
        while not cls._STOP:
            cls._flush_once()
            time.sleep(cls._FLUSH_INTERVAL_SEC)

    @classmethod
    def _flush_once(cls) -> None:
        if cls._TRACE_PATH is None:
            return
        batch: list[str] = []
        with cls._BUFFER_LOCK:
            while cls._BUFFER and len(batch) < cls._BATCH_SIZE:
                batch.append(cls._BUFFER.popleft())
        if not batch:
            return
        with cls._TRACE_PATH.open("a", encoding="utf-8") as f:
            for line in batch:
                f.write(line)
                f.write("\n")
        for redis_client in cls._REDIS_CLIENTS:
            try:
                for line in batch:
                    redis_client.lpush("trace:runtime", line)
            except Exception:
                continue

    @classmethod
    def _spill(cls, line: str) -> None:
        if cls._SPILL_PATH is None:
            return
        with cls._SPILL_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")

    @classmethod
    def shutdown(cls) -> None:
        cls._STOP = True
        if cls._FLUSH_THREAD is not None and cls._FLUSH_THREAD.is_alive():
            cls._FLUSH_THREAD.join(timeout=2.0)
        cls._flush_once()

    def emit(
        self,
        trace_event: str,
        *,
        execution_hash: str,
        task_id: str,
        video_id: str,
        component_name: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "trace_event": trace_event,
            "execution_hash": execution_hash,
            "task_id": task_id,
            "video_id": video_id,
            "timestamp": time.time(),
            "component_name": component_name,
            "extra": extra or {},
        }
        line = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        with self._BUFFER_LOCK:
            if len(self._BUFFER) >= self._MAX_BUFFER:
                # Spill oldest payload to protect hot paths from blocking.
                oldest = self._BUFFER.popleft()
                self._spill(oldest)
            self._BUFFER.append(line)
