from core.entity_graph import EntityGraph
from core.event_contract import EventContract
from core.temporal_index import TemporalIndex


class EventEnricher:
    def __init__(self) -> None:
        self.temporal_index = TemporalIndex()
        self.entity_graph = EntityGraph()

    @staticmethod
    def _choose_candidate_track(timestamp_sec: float, person_intervals: dict[str, tuple[float, float]]) -> str | None:
        candidates = [
            track_id for track_id, interval in person_intervals.items() if interval[0] <= timestamp_sec <= interval[1]
        ]
        if not candidates:
            return None
        return sorted(candidates)[0]

    def enrich(self, job_id: str, raw_events: list[EventContract]) -> list[dict]:
        normalized_events = self.temporal_index.normalize_events(raw_events)
        graph_state = self.entity_graph.build(job_id=job_id, events=normalized_events)

        enriched_events: list[dict] = []
        for event in normalized_events:
            enriched = dict(event)
            payload = dict(enriched.get("payload", {}))
            payload.setdefault("normalized_references", {})

            if event["event_type"] in {"person_track_start", "person_track_end", "person_detected"}:
                track_id = payload.get("track_id")
                if track_id and track_id in graph_state.track_to_entity_id:
                    payload["entity_id"] = graph_state.track_to_entity_id[track_id]

            if event["event_type"] == "speech_segment":
                ts = float(event["timestamp_sec"])
                candidate_track_id = self._choose_candidate_track(ts, graph_state.person_intervals)
                if candidate_track_id is not None:
                    payload["candidate_speaker_person_track_id"] = candidate_track_id
                    payload["candidate_speaker_entity_id"] = graph_state.track_to_entity_id.get(candidate_track_id)

            enriched["payload"] = payload
            enriched["unified_timestamp_sec"] = enriched["timestamp_sec"]
            enriched_events.append(enriched)

        return enriched_events
