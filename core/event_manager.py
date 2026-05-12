from threading import Lock
from time import monotonic

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from core.event_contract import EventContract
from db.models import Event


class EventManager:
    _BUFFER_LOCK = Lock()
    _FLUSH_LOCKS_LOCK = Lock()
    _EVENT_BUFFER: dict[str, list[EventContract]] = {}
    _LAST_FLUSH_AT: dict[str, float] = {}
    _JOB_FLUSH_LOCKS: dict[str, Lock] = {}
    _BUFFER_BATCH_SIZE = 20
    _BUFFER_FLUSH_INTERVAL_SEC = 3.0
    @staticmethod
    def _event_type_priority_expr():
        return case(
            (Event.event_type == "speech_segment", 0),
            (
                Event.event_type.in_(
                    [
                        "person_detected",
                        "person_track_start",
                        "person_track_end",
                        "object_detected",
                        "object_present",
                        "action_detected",
                    ]
                ),
                1,
            ),
            else_=2,
        )


    def __init__(self, db: Session) -> None:
        self.db = db

    def validate_event(self, event: dict | EventContract) -> EventContract:
        if isinstance(event, EventContract):
            return event
        return EventContract.model_validate(event)

    def _buffer_event(self, event: EventContract) -> None:
        with self._BUFFER_LOCK:
            job_buffer = self._EVENT_BUFFER.setdefault(event.job_id, [])
            if any(existing.event_id == event.event_id for existing in job_buffer):
                return
            job_buffer.append(event)
            self._LAST_FLUSH_AT.setdefault(event.job_id, monotonic())

    def _drain_job_buffer(self, job_id: str) -> list[EventContract]:
        with self._BUFFER_LOCK:
            events = self._EVENT_BUFFER.get(job_id, [])
            if not events:
                return []
            self._EVENT_BUFFER[job_id] = []
            self._LAST_FLUSH_AT[job_id] = monotonic()
            return list(events)

    def _get_flush_lock(self, job_id: str) -> Lock:
        with self._FLUSH_LOCKS_LOCK:
            if job_id not in self._JOB_FLUSH_LOCKS:
                self._JOB_FLUSH_LOCKS[job_id] = Lock()
            return self._JOB_FLUSH_LOCKS[job_id]

    def _should_flush_job(self, job_id: str) -> bool:
        with self._BUFFER_LOCK:
            buffered = self._EVENT_BUFFER.get(job_id, [])
            if len(buffered) >= self._BUFFER_BATCH_SIZE:
                return True
            if not buffered:
                return False
            last_flush = self._LAST_FLUSH_AT.get(job_id, monotonic())
            return (monotonic() - last_flush) >= self._BUFFER_FLUSH_INTERVAL_SEC

    def flush_due_buffers(self) -> None:
        with self._BUFFER_LOCK:
            job_ids = list(self._EVENT_BUFFER.keys())
        for job_id in job_ids:
            if self._should_flush_job(job_id):
                self.flush_job_buffer(job_id)

    def flush_job_buffer(self, job_id: str) -> list[EventContract]:
        flush_lock = self._get_flush_lock(job_id)
        with flush_lock:
            events = self._drain_job_buffer(job_id)
            if not events:
                return []
            return self.commit_event_batch(job_id, events)

    def flush_all_buffers(self) -> None:
        with self._BUFFER_LOCK:
            job_ids = list(self._EVENT_BUFFER.keys())
        for job_id in job_ids:
            self.flush_job_buffer(job_id)

    def store_event(self, event: dict | EventContract) -> EventContract:
        validated = self.validate_event(event)
        self._buffer_event(validated)
        self.flush_due_buffers()
        return validated

    def create_event(self, event: dict | EventContract) -> EventContract:
        validated = self.store_event(event)
        self.flush_job_buffer(validated.job_id)
        self.db.commit()
        return validated

    def commit_event_batch(self, job_id: str, events: list[dict | EventContract]) -> list[EventContract]:
        validated_events = [self.validate_event(event) for event in events]
        same_job_events = [event for event in validated_events if event.job_id == job_id]
        if not same_job_events:
            return []

        unique_by_event_id: dict[str, EventContract] = {}
        for event in same_job_events:
            unique_by_event_id[event.event_id] = event
        deduped_events = list(unique_by_event_id.values())

        existing_event_ids = set(
            self.db.execute(select(Event.event_id).where(Event.event_id.in_([event.event_id for event in deduped_events])))
            .scalars()
            .all()
        )
        to_insert = [event for event in deduped_events if event.event_id not in existing_event_ids]
        if not to_insert:
            return deduped_events

        to_insert.sort(key=lambda event: (event.timestamp_sec, event.event_id))

        try:
            with self.db.begin_nested():
                for event in to_insert:
                    self.db.add(
                        Event(
                            event_id=event.event_id,
                            job_id=event.job_id,
                            event_type=event.event_type,
                            timestamp_sec=event.timestamp_sec,
                            confidence=event.confidence,
                            source=event.source,
                            payload=event.payload,
                        )
                    )
                self.db.flush()
        except Exception:
            self.db.rollback()
            raise

        return deduped_events

    def query_events(self, job_id: str) -> list[EventContract]:
        priority = self._event_type_priority_expr()
        rows = self.db.execute(
            select(Event)
            .where(Event.job_id == job_id)
            .order_by(Event.timestamp_sec.asc(), priority.asc(), Event.created_at.asc())
        ).scalars()
        return [
            EventContract(
                event_id=row.event_id,
                job_id=row.job_id,
                event_type=row.event_type,
                timestamp_sec=row.timestamp_sec,
                confidence=row.confidence,
                source=row.source,
                payload=row.payload,
            )
            for row in rows
        ]

    def query_events_by_time_range(self, job_id: str, start: float, end: float) -> list[EventContract]:
        priority = self._event_type_priority_expr()
        rows = self.db.execute(
            select(Event)
            .where(Event.job_id == job_id, Event.timestamp_sec >= start, Event.timestamp_sec <= end)
            .order_by(Event.timestamp_sec.asc(), priority.asc(), Event.created_at.asc())
        ).scalars()
        return [
            EventContract(
                event_id=row.event_id,
                job_id=row.job_id,
                event_type=row.event_type,
                timestamp_sec=row.timestamp_sec,
                confidence=row.confidence,
                source=row.source,
                payload=row.payload,
            )
            for row in rows
        ]
