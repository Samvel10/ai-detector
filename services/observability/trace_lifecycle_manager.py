from __future__ import annotations

import signal
import time
from pathlib import Path

STOP = False


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


class TraceLifecycleManager:
    def __init__(
        self,
        trace_file: str = "storage/runtime_trace.jsonl",
        max_bytes: int = 50 * 1024 * 1024,
        retention_count: int = 5,
    ) -> None:
        self.trace_path = Path(trace_file)
        self.spill_path = self.trace_path.with_suffix(".spill.jsonl")
        self.max_bytes = max_bytes
        self.retention_count = retention_count

    def compact_spill(self) -> None:
        if not self.spill_path.exists():
            return
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as main_f:
            with self.spill_path.open("r", encoding="utf-8") as spill_f:
                for line in spill_f:
                    main_f.write(line)
        self.spill_path.unlink(missing_ok=True)

    def rotate_if_needed(self) -> None:
        if not self.trace_path.exists():
            return
        if self.trace_path.stat().st_size <= self.max_bytes:
            return
        ts = int(time.time())
        rotated = self.trace_path.with_name(f"{self.trace_path.stem}.{ts}{self.trace_path.suffix}")
        self.trace_path.rename(rotated)
        self.trace_path.touch()

    def enforce_retention(self) -> None:
        pattern = f"{self.trace_path.stem}.*{self.trace_path.suffix}"
        archives = sorted(self.trace_path.parent.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in archives[self.retention_count :]:
            old.unlink(missing_ok=True)

    def run_once(self) -> None:
        self.compact_spill()
        self.rotate_if_needed()
        self.enforce_retention()


def run_trace_lifecycle_manager(poll_interval_sec: float = 30.0) -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    manager = TraceLifecycleManager()
    while not STOP:
        manager.run_once()
        time.sleep(poll_interval_sec)


if __name__ == "__main__":
    run_trace_lifecycle_manager()
