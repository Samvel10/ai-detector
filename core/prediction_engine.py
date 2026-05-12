from collections import Counter

from core.graph_query_engine import GraphQueryEngine
from core.semantic_reasoner import SemanticReasoner


class PredictionEngine:
    def __init__(
        self,
        graph_query_engine: GraphQueryEngine,
        semantic_reasoner: SemanticReasoner,
    ) -> None:
        self.graph_query_engine = graph_query_engine
        self.semantic_reasoner = semantic_reasoner

    @staticmethod
    def _safe_probability(value: float) -> float:
        return max(0.0, min(1.0, value))

    def _build_context(self, video_id: str) -> dict:
        features = self.semantic_reasoner.build_features(video_id)
        scene = self.semantic_reasoner.build_scene_understanding(video_id)
        interactions = self.semantic_reasoner.build_interactions(video_id)
        timeline = self.semantic_reasoner.build_narrative_timeline(video_id)
        return {"features": features, "scene": scene, "interactions": interactions, "timeline": timeline}

    def predict_actions(self, video_id: str) -> list[dict]:
        context = self._build_context(video_id)
        features = context["features"]
        scene = context["scene"]
        participants = list(scene.get("participants", []))
        interaction_counts: Counter[str] = Counter()
        talking_counts: Counter[str] = Counter()
        for key, value in features.get("interaction_matrix", {}).items():
            source, _, interaction_type = key.split("|", 2)
            count = int(value.get("count", 0))
            interaction_counts[source] += count
            if interaction_type == "talking":
                talking_counts[source] += count

        predictions: list[dict] = []
        for entity_id in sorted(participants):
            total = max(1, interaction_counts.get(entity_id, 0))
            talking_ratio = talking_counts.get(entity_id, 0) / total

            predicted_action = "move_position"
            base_prob = 0.45
            reasons = ["baseline_mobility_pattern"]

            if talking_ratio >= 0.6:
                predicted_action = "start_speaking"
                base_prob = 0.75
                reasons = ["high_talking_interaction_ratio", f"talking_ratio={talking_ratio:.2f}"]
            elif interaction_counts.get(entity_id, 0) >= 3:
                predicted_action = "approach_person"
                base_prob = 0.65
                reasons = ["frequent_social_interactions", f"interaction_count={interaction_counts[entity_id]}"]
            elif scene.get("dominant_activity") == "observing":
                predicted_action = "move_position"
                base_prob = 0.6
                reasons = ["scene_dominant_activity_observing"]
            elif scene.get("dominant_activity") == "talking":
                predicted_action = "start_speaking"
                base_prob = 0.58
                reasons = ["scene_dominant_activity_talking"]

            predictions.append(
                {
                    "entity_id": entity_id,
                    "predicted_action": predicted_action,
                    "probability": self._safe_probability(base_prob),
                    "time_window": "next 5-30 seconds",
                    "reasoning_features": reasons
                    + [f"interaction_total={interaction_counts.get(entity_id, 0)}", f"speech_total={talking_counts.get(entity_id, 0)}"],
                }
            )

        predictions.sort(key=lambda item: (-item["probability"], item["entity_id"]))
        return predictions

    def predict_interactions(self, video_id: str) -> list[dict]:
        context = self._build_context(video_id)
        features = context["features"]
        current_interactions = context["interactions"]
        participants = sorted(context["scene"].get("participants", []))

        pair_counts: Counter[tuple[str, str, str]] = Counter()
        for key, value in features.get("interaction_matrix", {}).items():
            source, target, i_type = key.split("|", 2)
            pair_counts[(source, target, i_type)] += int(value.get("count", 0))

        predictions = []
        for source in participants:
            for target in participants:
                if source == target:
                    continue
                talking_count = pair_counts.get((source, target, "talking"), 0)
                observing_count = pair_counts.get((source, target, "observing"), 0)

                if talking_count > 0:
                    predictions.append(
                        {
                            "source_entity": source,
                            "target_entity": target,
                            "interaction_type": "talking",
                            "probability": self._safe_probability(0.55 + min(0.35, talking_count * 0.1)),
                            "expected_time_range": "next 5-20 seconds",
                        }
                    )
                elif observing_count > 0:
                    predictions.append(
                        {
                            "source_entity": source,
                            "target_entity": target,
                            "interaction_type": "observing",
                            "probability": self._safe_probability(0.45 + min(0.25, observing_count * 0.08)),
                            "expected_time_range": "next 10-30 seconds",
                        }
                    )
                

        predictions.sort(key=lambda item: (-item["probability"], item["source_entity"], item["target_entity"]))
        return predictions

    def predict_scene_evolution(self, video_id: str) -> dict:
        context = self._build_context(video_id)
        features = context["features"]
        scene = context["scene"]
        interactions = context["interactions"]
        timeline = context["timeline"]

        scene_type = str(scene.get("scene_type", "unknown"))
        participants = scene.get("participants", [])
        interaction_density = len(interactions) / max(1, len(timeline))
        temporal_density = sum(bucket.get("event_count", 0) for bucket in features.get("temporal_density_map", {}).values())

        likely_transition = scene_type
        stability = 0.6
        confidence = 0.6

        if scene_type == "meeting":
            if interaction_density >= 2.0:
                likely_transition = "discussion"
                stability = 0.78
                confidence = 0.74
            else:
                likely_transition = "meeting"
                stability = 0.72
                confidence = 0.68
        elif scene_type == "interview":
            likely_transition = "discussion" if interaction_density > 1.0 else "interview"
            stability = 0.7
            confidence = 0.66
        elif scene_type == "interaction":
            likely_transition = "exit" if len(participants) <= 1 else "discussion"
            stability = 0.58
            confidence = 0.55
        else:
            likely_transition = "unknown"
            stability = 0.5
            confidence = 0.5

        if temporal_density == 0:
            stability = 0.5
            confidence = 0.5

        return {
            "scene_type_stability": self._safe_probability(stability),
            "likely_scene_transition": f"{scene_type} -> {likely_transition}",
            "confidence": self._safe_probability(confidence),
            "time_window": "next 10-60 seconds",
        }
