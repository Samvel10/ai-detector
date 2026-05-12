from dataclasses import dataclass

from core.event_contract import EventContract


@dataclass
class TemporalIndex:
    default_fps: float = 1.0

    @staticmethod
    def normalize_seconds(value: float | int | str) -> float:
        return max(0.0, float(value))

    @staticmethod
    def frame_index_to_seconds(frame_index: int, fps: float) -> float:
        if fps <= 0:
            raise ValueError("fps must be greater than 0")
        return max(0.0, float(frame_index) / float(fps))

    def normalize_event(self, event: EventContract) -> dict:
        normalized = event.model_dump()
        normalized["timestamp_sec"] = self.normalize_seconds(normalized["timestamp_sec"])

        payload = dict(normalized.get("payload", {}))
        if "start_sec" in payload:
            payload["start_sec"] = self.normalize_seconds(payload["start_sec"])
        if "end_sec" in payload:
            payload["end_sec"] = self.normalize_seconds(payload["end_sec"])
        if "frame_index" in payload:
            fps = float(payload.get("fps", self.default_fps))
            payload["timestamp_sec"] = self.frame_index_to_seconds(int(payload["frame_index"]), fps)
        normalized["payload"] = payload
        return normalized

    def normalize_events(self, events: list[EventContract]) -> list[dict]:
        # Preserve canonical upstream ordering from EventManager:
        # timestamp_sec -> event_type_priority -> created_at.
        return [self.normalize_event(event) for event in events]
