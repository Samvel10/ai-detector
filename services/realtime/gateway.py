from __future__ import annotations

import asyncio
import json
import os
from hashlib import sha256
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from redis import Redis
from sqlalchemy import select

from core.event_enricher import EventEnricher
from core.event_manager import EventManager
from core.graph_query_engine import GraphQueryEngine
from core.intelligence_graph import IntelligenceGraph
from core.prediction_engine import PredictionEngine
from core.semantic_reasoner import SemanticReasoner
from db.models import Video
from db.session import SessionLocal
from services.realtime.event_streams import STREAM_TYPES

app = FastAPI(title="Realtime Gateway")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)


def _parse_stream_fields(fields: dict[str, str]) -> dict[str, Any]:
    return {
        "sequence_id": int(fields.get("sequence_id", "0")),
        "video_id": fields.get("video_id", ""),
        "stream_type": fields.get("stream_type", ""),
        "version_hash": fields.get("version_hash", ""),
        "payload": json.loads(fields.get("payload", "{}")),
    }


def _stream_key(video_id: str, stream_type: str) -> str:
    return f"stream:video:{video_id}:{stream_type}"


def _hash_payload(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _snapshot_payloads(video_id: str) -> dict[str, dict[str, Any]]:
    db = SessionLocal()
    try:
        video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
        if video is None:
            return {}
        event_manager = EventManager(db=db)
        enricher = EventEnricher()
        graph = IntelligenceGraph()
        graph_query = GraphQueryEngine()
        semantic = SemanticReasoner(event_manager=event_manager, graph_query_engine=graph_query)
        prediction = PredictionEngine(graph_query_engine=graph_query, semantic_reasoner=semantic)

        raw_events = event_manager.query_events(video_id)
        enriched = enricher.enrich(job_id=video_id, raw_events=raw_events)
        state = graph.build_or_update(job_id=video_id, enriched_events=enriched)

        return {
            "timeline": {"events": [event.model_dump() for event in raw_events]},
            "tracking": {
                "events": [
                    event
                    for event in enriched
                    if event.get("event_type") in {"person_detected", "person_track_start", "person_track_end"}
                ]
            },
            "graph": {
                "graph_version": state.graph_version,
                "node_count": len(state.nodes),
                "edge_count": len(state.edges),
            },
            "semantic": {
                "scene": semantic.build_scene_understanding(video_id),
                "interactions": semantic.build_interactions(video_id),
                "timeline": semantic.build_narrative_timeline(video_id),
            },
            "prediction": {
                "actions": prediction.predict_actions(video_id),
                "interactions": prediction.predict_interactions(video_id),
                "scene": prediction.predict_scene_evolution(video_id),
            },
        }
    finally:
        db.close()


async def _read_loop(websocket: WebSocket, video_id: str, stream_types: list[str], last_ids: dict[str, str]) -> None:
    stream_ids = {stype: last_ids.get(stype, "0-0") for stype in stream_types}
    synthetic_sequence = 0
    last_hash_by_stream: dict[str, str] = {}
    while True:
        streams = {_stream_key(video_id, stype): stream_ids[stype] for stype in stream_types}
        try:
            response = redis_client.xread(streams=streams, count=100, block=3000)
        except Exception:
            snapshots = _snapshot_payloads(video_id)
            if snapshots:
                for stream_type in stream_types:
                    payload = snapshots.get(stream_type)
                    if payload is None:
                        continue
                    version_hash = _hash_payload(payload)
                    if last_hash_by_stream.get(stream_type) == version_hash:
                        continue
                    synthetic_sequence += 1
                    await websocket.send_json(
                        {
                            "type": "event",
                            "id": f"synthetic-{stream_type}-{synthetic_sequence}",
                            "sequence_id": synthetic_sequence,
                            "video_id": video_id,
                            "stream_type": stream_type,
                            "version_hash": version_hash,
                            "payload": payload,
                        }
                    )
                    last_hash_by_stream[stream_type] = version_hash
            else:
                await websocket.send_json({"type": "heartbeat", "status": "redis_unavailable"})
            await asyncio.sleep(1.0)
            continue
        if not response:
            await websocket.send_json({"type": "heartbeat"})
            continue
        for stream_name, entries in response:
            for entry_id, fields in entries:
                parsed = _parse_stream_fields(fields)
                await websocket.send_json({"type": "event", "id": entry_id, **parsed})
                stream_type = parsed["stream_type"]
                if stream_type in stream_ids:
                    stream_ids[stream_type] = entry_id


@app.websocket("/ws/videos/{video_id}")
async def ws_video(websocket: WebSocket, video_id: str) -> None:
    await websocket.accept()
    try:
        initial = await websocket.receive_json()
        stream_types = initial.get("streams", list(STREAM_TYPES))
        stream_types = [stream for stream in stream_types if stream in STREAM_TYPES]
        if not stream_types:
            stream_types = list(STREAM_TYPES)
        last_ids = initial.get("last_ids", {})
        await websocket.send_json({"type": "connected", "video_id": video_id, "streams": stream_types})
        await _read_loop(websocket, video_id=video_id, stream_types=stream_types, last_ids=last_ids)
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011)


@app.websocket("/ws")
async def ws_health(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        initial = await websocket.receive_json()
        video_id = str(initial.get("video_id", "")).strip()
        stream_types = initial.get("streams", list(STREAM_TYPES))
        stream_types = [stream for stream in stream_types if stream in STREAM_TYPES]
        if not stream_types:
            stream_types = list(STREAM_TYPES)
        last_ids = initial.get("last_ids", {})
        if video_id:
            await websocket.send_json({"type": "connected", "video_id": video_id, "streams": stream_types})
            await _read_loop(websocket, video_id=video_id, stream_types=stream_types, last_ids=last_ids)
            return
        await websocket.send_json({"type": "connected", "mode": "gateway-health"})
        while True:
            await websocket.send_json({"type": "heartbeat"})
            await asyncio.sleep(3.0)
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011)
