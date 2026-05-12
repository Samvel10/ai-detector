from dataclasses import asdict

from core.intelligence_graph import IntelligenceGraph


class GraphQueryEngine:
    def __init__(self) -> None:
        self.graph = IntelligenceGraph()

    def get_person_timeline(self, job_id: str, entity_id: str, start_sec: float | None = None, end_sec: float | None = None) -> dict:
        timeline = self.graph.get_person_timeline(job_id, entity_id)
        items = timeline.get("timeline", [])
        if start_sec is not None:
            items = [item for item in items if float(item["timestamp_sec"]) >= float(start_sec)]
        if end_sec is not None:
            items = [item for item in items if float(item["timestamp_sec"]) <= float(end_sec)]
        timeline["timeline"] = items
        return timeline

    def get_speech_by_person(
        self, job_id: str, entity_id: str, start_sec: float | None = None, end_sec: float | None = None
    ) -> list[dict]:
        speech_nodes = self.graph.get_speech_by_person(job_id, entity_id)
        filtered = speech_nodes
        if start_sec is not None:
            filtered = [node for node in filtered if float(node["attributes"].get("start_sec", 0.0)) >= float(start_sec)]
        if end_sec is not None:
            filtered = [node for node in filtered if float(node["attributes"].get("end_sec", 0.0)) <= float(end_sec)]
        return filtered

    def get_interactions(
        self, job_id: str, entity_id: str, start_sec: float | None = None, end_sec: float | None = None
    ) -> list[dict]:
        interactions = self.graph.get_interactions(job_id, entity_id)
        if start_sec is not None:
            interactions = [edge for edge in interactions if float(edge["timestamp_sec"]) >= float(start_sec)]
        if end_sec is not None:
            interactions = [edge for edge in interactions if float(edge["timestamp_sec"]) <= float(end_sec)]
        return interactions

    def traverse_neighbors(self, job_id: str, entity_id: str, max_depth: int = 1) -> dict:
        state = self.graph.load_snapshot(job_id)
        if state is None:
            return {"entity_id": entity_id, "neighbors": []}
        root_node_id = self.graph._node_id(job_id, "PersonEntity", entity_id)
        if root_node_id not in state.nodes:
            return {"entity_id": entity_id, "neighbors": []}

        frontier = {root_node_id}
        visited = set(frontier)
        neighbors = []
        depth = 0
        while frontier and depth < max_depth:
            next_frontier = set()
            for edge in state.edges:
                if edge.from_node_id in frontier and edge.to_node_id not in visited:
                    visited.add(edge.to_node_id)
                    next_frontier.add(edge.to_node_id)
                    neighbors.append({"node": asdict(state.nodes.get(edge.to_node_id, state.nodes[root_node_id])), "edge": asdict(edge)})
                if edge.to_node_id in frontier and edge.from_node_id not in visited:
                    visited.add(edge.from_node_id)
                    next_frontier.add(edge.from_node_id)
                    neighbors.append({"node": asdict(state.nodes.get(edge.from_node_id, state.nodes[root_node_id])), "edge": asdict(edge)})
            frontier = next_frontier
            depth += 1
        return {"entity_id": entity_id, "neighbors": neighbors}
