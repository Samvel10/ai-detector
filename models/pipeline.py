from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from models.action import ActionPrediction, ActionRecognizer
from models.common import load_models_config
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
        cfg = load_models_config().get("person_object", {})
        # Objects need a stricter threshold than person detection: generic YOLO
        # produces many false positives (microwave/skateboard) on out-of-domain frames.
        self._object_conf_threshold = float(cfg.get("object_conf_threshold", 0.55))

    def analyze_frames(self, frame_files: list[Path], fps: float) -> VisionPipelineResult:
        aggregator = TrackAggregator()
        # Aggregate object detections by (label, track_id) so a "microwave"
        # detected on 34 consecutive frames produces 1 event with
        # observation_count=34, not 34 noisy events.
        object_tracks: dict[tuple[str, str], dict] = {}
        anon_counter = 0
        frames: list[FrameDetections] = []
        frame_paths_by_track: dict[str, list[Path]] = {}

        for frame_index, frame_path in enumerate(frame_files):
            timestamp_sec = frame_index / fps
            frame = self.detector.track_frame(frame_path, timestamp_sec, persist=True)
            frames.append(frame)
            aggregator.ingest(frame, person_class_id=self._person_class_id)
            for detection in frame.detections:
                if detection.cls_id != self._person_class_id:
                    if detection.confidence < self._object_conf_threshold:
                        continue
                    track_id = detection.track_id
                    if track_id:
                        key = (detection.label, track_id)
                    else:
                        anon_counter += 1
                        key = (detection.label, f"anon-{anon_counter}")
                    existing = object_tracks.get(key)
                    if existing is None:
                        object_tracks[key] = {
                            "label": detection.label,
                            "track_id": track_id,
                            "first_sec": timestamp_sec,
                            "last_sec": timestamp_sec,
                            "best_confidence": detection.confidence,
                            "first_bbox": list(detection.bbox),
                            "last_bbox": list(detection.bbox),
                            "frame_width": frame.frame_width,
                            "frame_height": frame.frame_height,
                            "observation_count": 1,
                        }
                    else:
                        existing["last_sec"] = timestamp_sec
                        if detection.confidence > existing["best_confidence"]:
                            existing["best_confidence"] = detection.confidence
                            existing["last_bbox"] = list(detection.bbox)
                        existing["observation_count"] += 1
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

        # Flatten aggregated object tracks into events (one per track, not per frame).
        object_events: list[dict] = []
        for track_info in object_tracks.values():
            object_events.append(
                {
                    "timestamp_sec": track_info["first_sec"],
                    "confidence": track_info["best_confidence"],
                    "label": track_info["label"],
                    "bbox": track_info["last_bbox"],
                    "frame_width": track_info["frame_width"],
                    "frame_height": track_info["frame_height"],
                    "first_seen_sec": track_info["first_sec"],
                    "last_seen_sec": track_info["last_sec"],
                    "observation_count": track_info["observation_count"],
                    "track_id": track_info["track_id"],
                }
            )

        return VisionPipelineResult(
            frames=frames,
            tracks=tracks,
            object_events=object_events,
            action_by_track=action_by_track,
        )
