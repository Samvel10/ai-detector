import hashlib
from dataclasses import dataclass, field


@dataclass
class PersonEntity:
    entity_id: str
    person_track_id: str
    start_sec: float
    end_sec: float
    source_event_ids: list[str] = field(default_factory=list)


@dataclass
class AudioSpeakerEntity:
    entity_id: str
    speech_event_id: str
    timestamp_sec: float
    candidate_person_track_id: str | None = None
    candidate_person_entity_id: str | None = None


@dataclass
class EntityGraphState:
    person_entities: dict[str, PersonEntity]
    audio_speakers: dict[str, AudioSpeakerEntity]
    person_intervals: dict[str, tuple[float, float]]
    track_to_entity_id: dict[str, str]


class EntityGraph:
    @staticmethod
    def _person_entity_id(job_id: str, track_id: str) -> str:
        digest = hashlib.sha1(f"{job_id}:person:{track_id}".encode("utf-8")).hexdigest()[:12]
        return f"person-{digest}"

    @staticmethod
    def _audio_entity_id(job_id: str, event_id: str) -> str:
        digest = hashlib.sha1(f"{job_id}:audio:{event_id}".encode("utf-8")).hexdigest()[:12]
        return f"audio-{digest}"

    def build(self, job_id: str, events: list[dict]) -> EntityGraphState:
        person_entities: dict[str, PersonEntity] = {}
        audio_speakers: dict[str, AudioSpeakerEntity] = {}
        starts: dict[str, tuple[float, str]] = {}
        ends: dict[str, tuple[float, str]] = {}

        for event in events:
            payload = event.get("payload", {})
            track_id = payload.get("track_id")
            if not track_id:
                continue
            if event["event_type"] == "person_track_start":
                starts[track_id] = (float(event["timestamp_sec"]), event["event_id"])
            elif event["event_type"] == "person_track_end":
                ends[track_id] = (float(event["timestamp_sec"]), event["event_id"])

        person_intervals: dict[str, tuple[float, float]] = {}
        track_to_entity_id: dict[str, str] = {}
        for track_id, (start_sec, start_event_id) in starts.items():
            end_sec, end_event_id = ends.get(track_id, (start_sec, start_event_id))
            entity_id = self._person_entity_id(job_id, track_id)
            person_entities[entity_id] = PersonEntity(
                entity_id=entity_id,
                person_track_id=track_id,
                start_sec=start_sec,
                end_sec=end_sec,
                source_event_ids=[start_event_id, end_event_id],
            )
            person_intervals[track_id] = (start_sec, end_sec)
            track_to_entity_id[track_id] = entity_id

        for event in events:
            if event["event_type"] != "speech_segment":
                continue
            speech_id = event["event_id"]
            audio_entity_id = self._audio_entity_id(job_id, speech_id)
            audio_speakers[audio_entity_id] = AudioSpeakerEntity(
                entity_id=audio_entity_id,
                speech_event_id=speech_id,
                timestamp_sec=float(event["timestamp_sec"]),
            )

        return EntityGraphState(
            person_entities=person_entities,
            audio_speakers=audio_speakers,
            person_intervals=person_intervals,
            track_to_entity_id=track_to_entity_id,
        )
