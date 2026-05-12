from core.event_enricher import EventEnricher
from core.event_manager import EventManager
from core.graph_query_engine import GraphQueryEngine
from core.intelligence_contract import IntelligenceContract


class SemanticReasoner:
    def __init__(self, event_manager: EventManager, graph_query_engine: GraphQueryEngine) -> None:
        self.event_manager = event_manager
        self.graph_query_engine = graph_query_engine
        self.enricher = EventEnricher()

    def _load_enriched_events(self, video_id: str) -> list[dict]:
        raw_events = self.event_manager.query_events(video_id)
        return self.enricher.enrich(job_id=video_id, raw_events=raw_events)

    def build_features(self, video_id: str) -> dict:
        enriched_events = self._load_enriched_events(video_id)
        raw_events = self.event_manager.query_events(video_id)
        return IntelligenceContract.build_intelligence_features(
            events=raw_events,
            graph=self.graph_query_engine,
            enriched_events=enriched_events,
            job_id=video_id,
        )

    def build_scene_understanding(self, video_id: str) -> dict:
        features = self.build_features(video_id)
        scene = IntelligenceContract.infer_scene(features)
        behavior_patterns = IntelligenceContract.infer_behavior_patterns(features)
        return {
            "scene_type": scene["scene_type"],
            "participants": scene["participants"],
            "dominant_activity": scene["dominant_activity"],
            "behavior_patterns": behavior_patterns,
        }

    def build_interactions(self, video_id: str) -> list[dict]:
        features = self.build_features(video_id)
        return IntelligenceContract.infer_interactions(features)

    def build_narrative_timeline(self, video_id: str) -> list[dict]:
        features = self.build_features(video_id)
        return IntelligenceContract.build_timeline_segments(features)

    def build_behavior_patterns(self, video_id: str, enriched_events: list[dict] | None = None) -> list[dict]:
        if enriched_events is not None:
            raw_events = self.event_manager.query_events(video_id)
            features = IntelligenceContract.build_intelligence_features(
                events=raw_events,
                graph=self.graph_query_engine,
                enriched_events=enriched_events,
                job_id=video_id,
            )
        else:
            features = self.build_features(video_id)
        return IntelligenceContract.infer_behavior_patterns(features)
