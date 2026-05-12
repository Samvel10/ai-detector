import hashlib
import json
from collections import Counter, defaultdict


class IntelligenceContract:
    _FEATURE_CACHE: dict[tuple[str, str], dict] = {}

    @staticmethod
    def _stable_person_entity_id(job_id: str, track_id: str) -> str:
        digest = hashlib.sha1(f"{job_id}:person:{track_id}".encode("utf-8")).hexdigest()[:12]
        return f"person-{digest}"

    @staticmethod
    def _event_hash(enriched_events: list[dict]) -> str:
        canonical = [
            {
                "event_id": e.get("event_id"),
                "event_type": e.get("event_type"),
                "timestamp_sec": float(e.get("timestamp_sec", 0.0)),
                "confidence": float(e.get("confidence", 0.0)),
                "payload": e.get("payload", {}),
            }
            for e in enriched_events
        ]
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def resolve_entities(cls, job_id: str, enriched_events: list[dict]) -> dict:
        track_to_entity: dict[str, str] = {}
        for event in enriched_events:
            payload = event.get("payload", {})
            track_id = payload.get("track_id")
            entity_id = payload.get("entity_id")
            if track_id and entity_id:
                track_to_entity[str(track_id)] = str(entity_id)

        for event in enriched_events:
            payload = event.get("payload", {})
            candidate_track = payload.get("candidate_speaker_person_track_id")
            candidate_entity = payload.get("candidate_speaker_entity_id")
            if candidate_track and candidate_entity:
                track_to_entity[str(candidate_track)] = str(candidate_entity)

        for event in enriched_events:
            payload = event.get("payload", {})
            track_id = payload.get("track_id")
            if track_id and str(track_id) not in track_to_entity:
                track_to_entity[str(track_id)] = cls._stable_person_entity_id(job_id, str(track_id))

        event_to_entity: dict[str, str] = {}
        for event in enriched_events:
            payload = event.get("payload", {})
            if payload.get("entity_id"):
                event_to_entity[str(event.get("event_id"))] = str(payload.get("entity_id"))
            elif payload.get("track_id") and str(payload.get("track_id")) in track_to_entity:
                event_to_entity[str(event.get("event_id"))] = track_to_entity[str(payload.get("track_id"))]
            elif payload.get("candidate_speaker_person_track_id") and str(
                payload.get("candidate_speaker_person_track_id")
            ) in track_to_entity:
                event_to_entity[str(event.get("event_id"))] = track_to_entity[
                    str(payload.get("candidate_speaker_person_track_id"))
                ]

        return {"track_to_entity": track_to_entity, "event_to_entity": event_to_entity}

    @classmethod
    def build_intelligence_features(cls, events, graph, enriched_events: list[dict], job_id: str) -> dict:
        event_hash = cls._event_hash(enriched_events)
        cache_key = (job_id, event_hash)
        if cache_key in cls._FEATURE_CACHE:
            return cls._FEATURE_CACHE[cache_key]

        resolved = cls.resolve_entities(job_id=job_id, enriched_events=enriched_events)
        track_to_entity = resolved["track_to_entity"]
        event_to_entity = resolved["event_to_entity"]

        entity_activity_map: dict[str, dict] = defaultdict(lambda: {"speech_events": 0, "presence_events": 0, "total": 0})
        speech_activity_map: dict[str, dict] = defaultdict(
            lambda: {"speech_count": 0, "total_speech_duration": 0.0, "avg_confidence": 0.0, "confidence_acc": 0.0}
        )
        interaction_matrix: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "confidence_acc": 0.0, "time_ranges": [], "interaction_type": ""}
        )
        temporal_density_map: dict[int, dict] = defaultdict(
            lambda: {"event_count": 0, "speech_count": 0, "person_count": 0, "entities": set(), "events": []}
        )

        participants = set()
        for event in enriched_events:
            event_id = str(event.get("event_id"))
            event_type = str(event.get("event_type", ""))
            timestamp = float(event.get("timestamp_sec", 0.0))
            confidence = float(event.get("confidence", 0.0))
            payload = event.get("payload", {})
            bucket = int(timestamp // 10.0)
            entity_id = event_to_entity.get(event_id)

            if entity_id:
                participants.add(entity_id)
                entity_activity_map[entity_id]["total"] += 1
                temporal_density_map[bucket]["entities"].add(entity_id)

            temporal_density_map[bucket]["event_count"] += 1
            temporal_density_map[bucket]["events"].append(event)

            if event_type in {"person_detected", "person_track_start", "person_track_end"}:
                if entity_id:
                    entity_activity_map[entity_id]["presence_events"] += 1
                temporal_density_map[bucket]["person_count"] += 1

            if event_type == "speech_segment":
                temporal_density_map[bucket]["speech_count"] += 1
                speaker_entity = payload.get("candidate_speaker_entity_id")
                if not speaker_entity:
                    candidate_track = payload.get("candidate_speaker_person_track_id")
                    if candidate_track:
                        speaker_entity = track_to_entity.get(str(candidate_track))
                if speaker_entity:
                    speaker_entity = str(speaker_entity)
                    participants.add(speaker_entity)
                    start_sec = float(payload.get("start_sec", timestamp))
                    end_sec = float(payload.get("end_sec", timestamp))
                    duration = max(0.0, end_sec - start_sec)
                    speech_activity_map[speaker_entity]["speech_count"] += 1
                    speech_activity_map[speaker_entity]["total_speech_duration"] += duration
                    speech_activity_map[speaker_entity]["confidence_acc"] += confidence
                    entity_activity_map[speaker_entity]["speech_events"] += 1
                    entity_activity_map[speaker_entity]["total"] += 1

                    for target_entity in sorted(participants):
                        if target_entity == speaker_entity:
                            continue
                        key = f"{speaker_entity}|{target_entity}|talking"
                        interaction_matrix[key]["count"] += 1
                        interaction_matrix[key]["confidence_acc"] += confidence
                        interaction_matrix[key]["time_ranges"].append([start_sec, end_sec])
                        interaction_matrix[key]["interaction_type"] = "talking"

        # Deterministic observing interactions from overlapping presence windows.
        participant_list = sorted(participants)
        intervals: dict[str, tuple[float, float]] = {}
        for entity_id in participant_list:
            timeline = graph.get_person_timeline(job_id, entity_id)
            edge_times = [float(edge["timestamp_sec"]) for edge in timeline.get("timeline", [])]
            if edge_times:
                intervals[entity_id] = (min(edge_times), max(edge_times))

        for idx, source in enumerate(sorted(intervals.keys())):
            src_range = intervals[source]
            for target in sorted(intervals.keys())[idx + 1 :]:
                tgt_range = intervals[target]
                overlap_start = max(src_range[0], tgt_range[0])
                overlap_end = min(src_range[1], tgt_range[1])
                if overlap_start <= overlap_end:
                    key = f"{source}|{target}|observing"
                    interaction_matrix[key]["count"] += 1
                    interaction_matrix[key]["confidence_acc"] += 0.6
                    interaction_matrix[key]["time_ranges"].append([overlap_start, overlap_end])
                    interaction_matrix[key]["interaction_type"] = "observing"

        for entity_id in sorted(speech_activity_map.keys()):
            speech_count = speech_activity_map[entity_id]["speech_count"]
            if speech_count > 0:
                speech_activity_map[entity_id]["avg_confidence"] = (
                    speech_activity_map[entity_id]["confidence_acc"] / speech_count
                )
            del speech_activity_map[entity_id]["confidence_acc"]

        normalized_temporal_density_map = {}
        for bucket, value in sorted(temporal_density_map.items(), key=lambda item: item[0]):
            normalized_temporal_density_map[bucket] = {
                "event_count": value["event_count"],
                "speech_count": value["speech_count"],
                "person_count": value["person_count"],
                "entities": sorted(value["entities"]),
                "events": value["events"],
            }

        features = {
            "job_id": job_id,
            "event_hash": event_hash,
            "entity_activity_map": {k: dict(v) for k, v in sorted(entity_activity_map.items(), key=lambda item: item[0])},
            "speech_activity_map": {k: dict(v) for k, v in sorted(speech_activity_map.items(), key=lambda item: item[0])},
            "interaction_matrix": {k: dict(v) for k, v in sorted(interaction_matrix.items(), key=lambda item: item[0])},
            "temporal_density_map": normalized_temporal_density_map,
            "participants": sorted(participants),
            "resolved_entities": resolved,
            "event_count": len(enriched_events),
        }
        cls._FEATURE_CACHE[cache_key] = features
        return features

    @staticmethod
    def infer_interactions(features: dict) -> list[dict]:
        interactions = []
        for key, value in features.get("interaction_matrix", {}).items():
            source, target, interaction_type = key.split("|", 2)
            count = int(value.get("count", 0))
            confidence_acc = float(value.get("confidence_acc", 0.0))
            time_ranges = value.get("time_ranges", [])
            avg_conf = confidence_acc / count if count > 0 else 0.0
            merged_start = min((tr[0] for tr in time_ranges), default=0.0)
            merged_end = max((tr[1] for tr in time_ranges), default=merged_start)
            interactions.append(
                {
                    "source_entity": source,
                    "target_entity": target,
                    "interaction_type": interaction_type,
                    "confidence": max(0.0, min(1.0, avg_conf)),
                    "time_range": [merged_start, merged_end],
                }
            )
        interactions.sort(key=lambda item: (item["time_range"][0], item["source_entity"], item["target_entity"]))
        return interactions

    @staticmethod
    def infer_scene(features: dict) -> dict:
        participants = list(features.get("participants", []))
        speech_count = sum(v.get("speech_count", 0) for v in features.get("speech_activity_map", {}).values())
        person_presence_count = sum(v.get("presence_events", 0) for v in features.get("entity_activity_map", {}).values())

        if len(participants) >= 2 and speech_count >= 2:
            scene_type = "meeting"
        elif len(participants) == 2 and speech_count >= 1:
            scene_type = "interview"
        elif len(participants) >= 2 and person_presence_count > 0:
            scene_type = "interaction"
        else:
            scene_type = "unknown"

        if speech_count >= person_presence_count and speech_count > 0:
            dominant_activity = "talking"
        elif person_presence_count > 0:
            dominant_activity = "observing"
        else:
            dominant_activity = "unknown"

        confidence = 0.5
        if features.get("event_count", 0) > 0:
            confidence = min(1.0, 0.4 + (min(50, features["event_count"]) / 100))

        return {
            "scene_type": scene_type,
            "dominant_activity": dominant_activity,
            "participants": sorted(participants),
            "confidence": confidence,
        }

    @staticmethod
    def build_timeline_segments(features: dict) -> list[dict]:
        segments = []
        for bucket, data in sorted(features.get("temporal_density_map", {}).items(), key=lambda item: item[0]):
            start = bucket * 10.0
            end = (bucket + 1) * 10.0
            speech_count = int(data.get("speech_count", 0))
            person_count = int(data.get("person_count", 0))
            events = data.get("events", [])
            avg_conf = 0.0
            if events:
                avg_conf = sum(float(e.get("confidence", 0.0)) for e in events) / len(events)

            if speech_count > 0 and person_count > 0:
                summary = "People are present and speaking."
            elif speech_count > 0:
                summary = "Speech activity is detected."
            elif person_count > 0:
                summary = "People are present in the scene."
            else:
                summary = "Low semantic activity."

            segments.append(
                {
                    "summary_text": summary,
                    "involved_entities": sorted(data.get("entities", [])),
                    "time_range": [start, end],
                    "confidence": avg_conf,
                }
            )
        return segments

    @staticmethod
    def infer_behavior_patterns(features: dict) -> list[dict]:
        patterns: list[dict] = []
        speech_map = features.get("speech_activity_map", {})
        if speech_map:
            speech_counts = {entity_id: int(data.get("speech_count", 0)) for entity_id, data in speech_map.items()}
            total_speech = sum(speech_counts.values())
            if total_speech > 0:
                dominant_entity = sorted(speech_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
                dominant_ratio = speech_counts[dominant_entity] / total_speech
                if dominant_ratio >= 0.6:
                    patterns.append(
                        {
                            "pattern_type": "repeated_speaking_dominance",
                            "entity_id": dominant_entity,
                            "confidence": min(1.0, dominant_ratio),
                        }
                    )

        participants = list(features.get("participants", []))
        outgoing_interactions = Counter()
        for key, value in features.get("interaction_matrix", {}).items():
            source, _, _ = key.split("|", 2)
            outgoing_interactions[source] += int(value.get("count", 0))

        for entity_id in sorted(participants):
            if outgoing_interactions.get(entity_id, 0) == 0:
                patterns.append(
                    {
                        "pattern_type": "isolated_person_behavior",
                        "entity_id": entity_id,
                        "confidence": 0.7,
                    }
                )

        object_usage_counter: Counter[str] = Counter()
        for bucket_data in features.get("temporal_density_map", {}).values():
            for event in bucket_data.get("events", []):
                if event.get("event_type") not in {"object_detected", "object_present"}:
                    continue
                payload = event.get("payload", {})
                object_id = payload.get("object_instance_id") or payload.get("object_id")
                if object_id:
                    object_usage_counter[str(object_id)] += 1

        for object_id, count in sorted(object_usage_counter.items(), key=lambda item: (-item[1], item[0])):
            if count >= 3:
                patterns.append(
                    {
                        "pattern_type": "object_usage_pattern",
                        "object_id": object_id,
                        "usage_count": count,
                        "confidence": min(1.0, 0.3 + (count * 0.1)),
                    }
                )

        return patterns
