import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from core.config import settings


class EntityLifecycleState(str, Enum):
    created = "created"
    active = "active"
    inactive = "inactive"
    merged = "merged"


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    job_id: str
    lifecycle_state: str = EntityLifecycleState.created.value
    confidence_accumulator: float = 0.0
    confidence_count: int = 0
    attributes: dict = field(default_factory=dict)
    merged_into: str | None = None
    updated_at_sec: float = 0.0

    @property
    def confidence_avg(self) -> float:
        if self.confidence_count <= 0:
            return 0.0
        return self.confidence_accumulator / self.confidence_count


@dataclass
class GraphEdge:
    edge_id: str
    edge_type: str
    from_node_id: str
    to_node_id: str
    timestamp_sec: float
    confidence: float
    weight: float = 0.0
    reinforcement_count: int = 1
    attributes: dict = field(default_factory=dict)


@dataclass
class IntelligenceGraphState:
    job_id: str
    graph_version: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    person_to_speech: dict[str, list[str]] = field(default_factory=dict)
    speech_to_person: dict[str, str] = field(default_factory=dict)


class IntelligenceGraph:
    def __init__(self) -> None:
        self.snapshot_root = settings.storage_root_path / "intelligence_graph"

    def _snapshot_path(self, job_id: str) -> Path:
        return self.snapshot_root / f"{job_id}.json"

    @staticmethod
    def _node_id(job_id: str, node_type: str, reference: str) -> str:
        return f"{job_id}:{node_type}:{reference}"

    @staticmethod
    def _edge_id(job_id: str, edge_type: str, from_node_id: str, to_node_id: str, timestamp_sec: float) -> str:
        return f"{job_id}:{edge_type}:{from_node_id}:{to_node_id}:{timestamp_sec:.3f}"

    @staticmethod
    def canonical_event_type_priority(event_type: str) -> int:
        if event_type == "speech_segment":
            return 0
        if event_type in {
            "person_detected",
            "person_track_start",
            "person_track_end",
            "object_detected",
            "object_present",
            "action_detected",
        }:
            return 1
        return 2

    def canonical_order_events(self, enriched_events: list[dict]) -> list[dict]:
        # EventManager already enforces canonical ordering:
        # timestamp_sec -> event_type_priority -> created_at.
        # Preserve upstream order to avoid fallback reordering drift.
        return list(enriched_events)

    def compute_graph_version(self, ordered_events: list[dict]) -> str:
        canonical_stream = [
            {
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "timestamp_sec": float(event.get("unified_timestamp_sec", event.get("timestamp_sec", 0.0))),
                "confidence": float(event.get("confidence", 0.0)),
                "source": event.get("source"),
                "payload": event.get("payload", {}),
            }
            for event in ordered_events
        ]
        serialized = json.dumps(canonical_stream, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def load_snapshot(self, job_id: str) -> IntelligenceGraphState | None:
        snapshot_path = self._snapshot_path(job_id)
        if not snapshot_path.exists():
            return None
        with snapshot_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        state = IntelligenceGraphState(job_id=raw["job_id"], graph_version=raw["graph_version"])
        for node_id, node_data in raw.get("nodes", {}).items():
            state.nodes[node_id] = GraphNode(**node_data)
        state.edges = [GraphEdge(**edge_data) for edge_data in raw.get("edges", [])]
        state.person_to_speech = raw.get("person_to_speech", {})
        state.speech_to_person = raw.get("speech_to_person", {})
        return state

    def save_snapshot(self, state: IntelligenceGraphState) -> None:
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        sorted_nodes = {
            node_id: asdict(state.nodes[node_id]) for node_id in sorted(state.nodes.keys())
        }
        sorted_edges = sorted(
            state.edges,
            key=lambda edge: (
                float(edge.timestamp_sec),
                edge.edge_type,
                edge.from_node_id,
                edge.to_node_id,
                edge.edge_id,
            ),
        )
        normalized_person_to_speech = {
            node_id: sorted(speech_ids)
            for node_id, speech_ids in sorted(state.person_to_speech.items(), key=lambda item: item[0])
        }
        normalized_speech_to_person = {
            speech_id: person_id for speech_id, person_id in sorted(state.speech_to_person.items(), key=lambda item: item[0])
        }
        payload = {
            "job_id": state.job_id,
            "graph_version": state.graph_version,
            "nodes": sorted_nodes,
            "edges": [asdict(edge) for edge in sorted_edges],
            "person_to_speech": normalized_person_to_speech,
            "speech_to_person": normalized_speech_to_person,
        }
        with self._snapshot_path(state.job_id).open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)

    def _upsert_node(
        self,
        state: IntelligenceGraphState,
        node_id: str,
        node_type: str,
        confidence: float,
        attributes: dict,
        timestamp_sec: float,
        lifecycle_state: EntityLifecycleState,
        merged_into: str | None = None,
    ) -> None:
        node = state.nodes.get(node_id)
        if node is None:
            node = GraphNode(node_id=node_id, node_type=node_type, job_id=state.job_id)
            state.nodes[node_id] = node
        node.confidence_accumulator += float(confidence)
        node.confidence_count += 1
        node.attributes.update(attributes)
        node.updated_at_sec = max(node.updated_at_sec, float(timestamp_sec))
        node.lifecycle_state = lifecycle_state.value
        node.merged_into = merged_into

    def _upsert_edge(
        self,
        state: IntelligenceGraphState,
        edge_type: str,
        from_node_id: str,
        to_node_id: str,
        timestamp_sec: float,
        confidence: float,
        attributes: dict | None = None,
    ) -> None:
        edge_id = self._edge_id(state.job_id, edge_type, from_node_id, to_node_id, timestamp_sec)
        existing = next((edge for edge in state.edges if edge.edge_id == edge_id), None)
        if existing is None:
            state.edges.append(
                GraphEdge(
                    edge_id=edge_id,
                    edge_type=edge_type,
                    from_node_id=from_node_id,
                    to_node_id=to_node_id,
                    timestamp_sec=float(timestamp_sec),
                    confidence=float(confidence),
                    weight=float(confidence),
                    reinforcement_count=1,
                    attributes=attributes or {},
                )
            )
            return
        existing.reinforcement_count += 1
        existing.weight = min(1.0, existing.weight + float(confidence))
        existing.confidence = max(existing.confidence, float(confidence))
        if attributes:
            existing.attributes.update(attributes)

    def _resolve_person_entity_id(self, job_id: str, payload: dict) -> str | None:
        entity_id = payload.get("entity_id")
        if entity_id:
            return str(entity_id)
        track_id = payload.get("track_id")
        if track_id:
            digest = hashlib.sha1(f"{job_id}:person:{track_id}".encode("utf-8")).hexdigest()[:12]
            return f"person-{digest}"
        return None

    def build_or_update(self, job_id: str, enriched_events: list[dict]) -> IntelligenceGraphState:
        ordered_events = self.canonical_order_events(enriched_events)
        graph_version = self.compute_graph_version(ordered_events)
        existing = self.load_snapshot(job_id)
        if existing is not None and existing.graph_version == graph_version:
            return existing

        state = IntelligenceGraphState(job_id=job_id, graph_version=graph_version)
        for event in ordered_events:
            event_type = str(event.get("event_type", ""))
            ts = float(event.get("unified_timestamp_sec", event.get("timestamp_sec", 0.0)))
            confidence = float(event.get("confidence", 0.0))
            payload = dict(event.get("payload", {}))

            if event_type in {"person_track_start", "person_track_end", "person_detected"}:
                person_entity_id = self._resolve_person_entity_id(job_id, payload)
                if person_entity_id is None:
                    continue
                person_node_id = self._node_id(job_id, "PersonEntity", person_entity_id)
                lifecycle = (
                    EntityLifecycleState.inactive if event_type == "person_track_end" else EntityLifecycleState.active
                )
                self._upsert_node(
                    state,
                    person_node_id,
                    "PersonEntity",
                    confidence,
                    {"entity_id": person_entity_id, "track_id": payload.get("track_id")},
                    ts,
                    lifecycle,
                )
                self._upsert_edge(
                    state,
                    "appeared_in",
                    person_node_id,
                    self._node_id(job_id, "Video", job_id),
                    ts,
                    confidence,
                    {"event_id": event.get("event_id")},
                )

            elif event_type == "speech_segment":
                speech_node_id = self._node_id(job_id, "SpeechEventNode", str(event.get("event_id")))
                self._upsert_node(
                    state,
                    speech_node_id,
                    "SpeechEventNode",
                    confidence,
                    {
                        "event_id": event.get("event_id"),
                        "text": payload.get("text", ""),
                        "start_sec": payload.get("start_sec", ts),
                        "end_sec": payload.get("end_sec", ts),
                    },
                    ts,
                    EntityLifecycleState.active,
                )
                self._upsert_edge(
                    state,
                    "observed_with",
                    speech_node_id,
                    self._node_id(job_id, "Video", job_id),
                    ts,
                    confidence,
                    {"event_id": event.get("event_id")},
                )

                candidate_person_entity_id = payload.get("candidate_speaker_entity_id")
                if candidate_person_entity_id:
                    person_node_id = self._node_id(job_id, "PersonEntity", str(candidate_person_entity_id))
                    self._upsert_node(
                        state,
                        person_node_id,
                        "PersonEntity",
                        confidence,
                        {
                            "entity_id": candidate_person_entity_id,
                            "track_id": payload.get("candidate_speaker_person_track_id"),
                        },
                        ts,
                        EntityLifecycleState.active,
                    )
                    self._upsert_edge(
                        state,
                        "spoke_at",
                        person_node_id,
                        speech_node_id,
                        ts,
                        confidence,
                        {"event_id": event.get("event_id")},
                    )
                    self._upsert_edge(
                        state,
                        "observed_with",
                        speech_node_id,
                        person_node_id,
                        ts,
                        confidence,
                        {"event_id": event.get("event_id")},
                    )
                    state.speech_to_person[speech_node_id] = person_node_id
                    state.person_to_speech.setdefault(person_node_id, [])
                    if speech_node_id not in state.person_to_speech[person_node_id]:
                        state.person_to_speech[person_node_id].append(speech_node_id)

            elif event_type in {"object_detected", "object_present"}:
                object_node_id = self._node_id(job_id, "ObjectEventNode", str(event.get("event_id")))
                self._upsert_node(
                    state,
                    object_node_id,
                    "ObjectEventNode",
                    confidence,
                    {"event_id": event.get("event_id"), "payload": payload},
                    ts,
                    EntityLifecycleState.active,
                )
            elif event_type == "action_detected":
                action_node_id = self._node_id(job_id, "ActionEventNode", str(event.get("event_id")))
                self._upsert_node(
                    state,
                    action_node_id,
                    "ActionEventNode",
                    confidence,
                    {"event_id": event.get("event_id"), "payload": payload},
                    ts,
                    EntityLifecycleState.active,
                )
            elif event_type == "entity_merged":
                from_entity = payload.get("from_entity_id")
                into_entity = payload.get("into_entity_id")
                if from_entity and into_entity:
                    from_node_id = self._node_id(job_id, "PersonEntity", str(from_entity))
                    into_node_id = self._node_id(job_id, "PersonEntity", str(into_entity))
                    self._upsert_node(
                        state,
                        from_node_id,
                        "PersonEntity",
                        confidence,
                        {"entity_id": from_entity},
                        ts,
                        EntityLifecycleState.merged,
                        merged_into=into_node_id,
                    )
            elif event_type == "entity_split":
                source_entity = payload.get("entity_id")
                new_entity = payload.get("new_entity_id")
                if source_entity and new_entity:
                    self._upsert_node(
                        state,
                        self._node_id(job_id, "PersonEntity", str(source_entity)),
                        "PersonEntity",
                        confidence,
                        {"entity_id": source_entity},
                        ts,
                        EntityLifecycleState.active,
                    )
                    self._upsert_node(
                        state,
                        self._node_id(job_id, "PersonEntity", str(new_entity)),
                        "PersonEntity",
                        confidence,
                        {"entity_id": new_entity},
                        ts,
                        EntityLifecycleState.created,
                    )

        self.save_snapshot(state)
        return state

    def get_person_timeline(self, job_id: str, entity_id: str) -> dict:
        state = self.load_snapshot(job_id)
        if state is None:
            return {"entity_id": entity_id, "timeline": []}
        person_node_id = self._node_id(job_id, "PersonEntity", entity_id)
        node = state.nodes.get(person_node_id)
        if node is None:
            return {"entity_id": entity_id, "timeline": []}
        timeline_edges = [edge for edge in state.edges if edge.from_node_id == person_node_id or edge.to_node_id == person_node_id]
        timeline_edges.sort(key=lambda edge: edge.timestamp_sec)
        return {
            "entity_id": entity_id,
            "lifecycle_state": node.lifecycle_state,
            "confidence_avg": node.confidence_avg,
            "timeline": [asdict(edge) for edge in timeline_edges],
        }

    def get_speech_by_person(self, job_id: str, entity_id: str) -> list[dict]:
        state = self.load_snapshot(job_id)
        if state is None:
            return []
        person_node_id = self._node_id(job_id, "PersonEntity", entity_id)
        speech_ids = state.person_to_speech.get(person_node_id, [])
        nodes = [state.nodes[speech_id] for speech_id in speech_ids if speech_id in state.nodes]
        nodes.sort(key=lambda node: float(node.attributes.get("start_sec", 0.0)))
        return [asdict(node) for node in nodes]

    def get_interactions(self, job_id: str, entity_id: str) -> list[dict]:
        state = self.load_snapshot(job_id)
        if state is None:
            return []
        person_node_id = self._node_id(job_id, "PersonEntity", entity_id)
        interactions = [
            edge
            for edge in state.edges
            if edge.from_node_id == person_node_id and edge.edge_type in {"spoke_at", "interacted_with", "observed_with"}
        ]
        interactions.sort(key=lambda edge: edge.timestamp_sec)
        return [asdict(edge) for edge in interactions]
