from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from models.detection import Detection, FrameDetections


@dataclass
class TrackObservation:
    timestamp_sec: float
    bbox: list[float]
    confidence: float
    frame_width: int
    frame_height: int
    face_bbox: list[float] | None = None
    face_confidence: float | None = None
    face_embedding: list[float] | None = None


@dataclass
class TrackState:
    track_id: str
    start_sec: float
    last_sec: float
    observations: list[TrackObservation] = field(default_factory=list)
    best_conf: float = 0.0


class TrackAggregator:
    def __init__(self) -> None:
        self._tracks: dict[str, TrackState] = {}

    def ingest(self, frame: FrameDetections, person_class_id: int = 0) -> None:
        for detection in frame.detections:
            if detection.cls_id != person_class_id:
                continue
            track_id = detection.track_id or f"anon-{len(self._tracks) + 1}"
            state = self._tracks.get(track_id)
            observation = TrackObservation(
                timestamp_sec=frame.timestamp_sec,
                bbox=detection.bbox,
                confidence=detection.confidence,
                frame_width=frame.frame_width,
                frame_height=frame.frame_height,
            )
            if state is None:
                self._tracks[track_id] = TrackState(
                    track_id=track_id,
                    start_sec=frame.timestamp_sec,
                    last_sec=frame.timestamp_sec,
                    observations=[observation],
                    best_conf=detection.confidence,
                )
                continue
            state.last_sec = frame.timestamp_sec
            state.best_conf = max(state.best_conf, detection.confidence)
            state.observations.append(observation)

    def all_tracks(self) -> list[TrackState]:
        return list(self._tracks.values())

    def frame_paths_for_track(self, track: TrackState) -> list[Path]:
        return [Path(str(obs.timestamp_sec)) for obs in track.observations]
