from __future__ import annotations

import time
import os

from db.models import Task, TaskStatus


class RetryPolicyEngine:
    """
    Stateless retry policy authority:
    - retry eligibility
    - backoff calculation
    - terminal routing decision
    """

    TRANSIENT_MARKERS = ("timeout", "tempor", "network", "unavailable", "connection")
    MAX_ATTEMPTS = 5

    @staticmethod
    def _debug_assert_no_overlap(operation: str) -> None:
        if os.getenv("ORCHESTRATION_DEBUG", "0") == "1":
            forbidden = {"route", "queue", "lock", "execution"}
            if any(word in operation.lower() for word in forbidden):
                raise RuntimeError("RetryPolicyEngine boundary violation")

    def classify_retryable(self, task: Task) -> bool:
        self._debug_assert_no_overlap("retry_classification")
        message = (task.error_message or "").lower()
        retryable_override = bool(task.payload.get("retryable", False))
        return retryable_override or any(marker in message for marker in self.TRANSIENT_MARKERS)

    def current_attempt(self, task: Task) -> int:
        self._debug_assert_no_overlap("retry_attempt_read")
        return int(task.payload.get("retry_attempt", 0))

    def should_dead_letter(self, task: Task) -> bool:
        self._debug_assert_no_overlap("retry_deadletter_decision")
        return self.current_attempt(task) >= self.MAX_ATTEMPTS

    def next_backoff_sec(self, task: Task) -> float:
        self._debug_assert_no_overlap("retry_backoff_calc")
        attempts = self.current_attempt(task)
        return min(60.0, float(2**attempts))

    def can_retry_now(self, task: Task, now_sec: float | None = None) -> bool:
        self._debug_assert_no_overlap("retry_time_gate")
        now = time.time() if now_sec is None else now_sec
        next_retry_at = float(task.payload.get("next_retry_at", 0.0))
        return now >= next_retry_at

    def apply_retry_transition(self, task: Task, now_sec: float | None = None) -> None:
        self._debug_assert_no_overlap("retry_transition")
        now = time.time() if now_sec is None else now_sec
        attempts = self.current_attempt(task)
        task.status = TaskStatus.queued
        task.payload["retry_attempt"] = attempts + 1
        task.payload["next_retry_at"] = now + self.next_backoff_sec(task)

    def decision(self, task: Task, execution_active: bool) -> str:
        self._debug_assert_no_overlap("retry_decision")
        if execution_active:
            return "blocked_active_execution"
        if not self.classify_retryable(task):
            return "non_retryable"
        if self.should_dead_letter(task):
            return "dead_letter"
        if not self.can_retry_now(task):
            return "defer"
        return "enqueue"
