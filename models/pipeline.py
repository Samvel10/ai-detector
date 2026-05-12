from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from models.action import ActionPrediction, ActionRecognizer
from models.detection import FrameDetections, YoloVisionDetector
from models.face import FaceRecognizer
from models.tracking import TrackAggregator, TrackState

logger = logging.getLogger("video_analysis.models.pipeline")


@dataclass
class VisionPipelineResult:
    frames: list[FrameDetections]
    tracks: list[TrackState]
    object_events: list[dict]
    action_by_track: dict[str, ActionPrediction]


class VisionPipeline:
    def __init__(self) -> None:
        self.detector = YoloVisionDetector()
        self.face = FaceRecognizer()
        self.action = ActionRecognizer()
        self._person_class_id = 0

    def analyze_frames(self, frame_files: list[Path], fps: float) -> VisionPipelineResult:
        aggregator = TrackAggregator()
        object_events: list[dict] = []
        frames: list[FrameDetections] = []
        frame_paths_by_track: dict[str, list[Path]] = {}

        for frame_index, frame_path in enumerate(frame_files):
            timestamp_sec = frame_index / fps
            frame = self.detector.track_frame(frame_path, timestamp_sec, persist=True)
            frames.append(frame)
            aggregator.ingest(frame, person_class_id=self._person_class_id)
            for detection in frame.detections:
                if detection.cls_id != self._person_class_id:
                    object_events.append(
                        {
                            "timestamp_sec": timestamp_sec,
                            "confidence": detection.confidence,
                            "label": detection.label,
                            "bbox": detection.bbox,
                            "frame_width": frame.frame_width,
                            "frame_height": frame.frame_height,
                        }
                    )
                    continue

                track_id = detection.track_id
                if not track_id:
                    continue
                frame_paths_by_track.setdefault(track_id, []).append(frame_path)
                face = self.face.detect_in_frame(frame_path, detection.bbox)
                if face is None:
                    continue
                for track in aggregator.all_tracks():
                    if track.track_id != track_id or not track.observations:
                        continue
                    obs = track.observations[-1]
                    obs.face_bbox = face.bbox
                    obs.face_confidence = face.confidence
                    obs.face_embedding = face.embedding

        tracks = aggregator.all_tracks()
        action_by_track: dict[str, ActionPrediction] = {}
        for track in tracks:
            prediction = self.action.predict_track(frame_paths_by_track.get(track.track_id, []))
            if prediction is not None:
                action_by_track[track.track_id] = prediction

        return VisionPipelineResult(
            frames=frames,
            tracks=tracks,
            object_events=object_events,
            action_by_track=action_by_track,
        )
