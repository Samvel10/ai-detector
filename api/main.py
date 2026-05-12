import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.event_enricher import EventEnricher
from core.graph_query_engine import GraphQueryEngine
from core.intelligence_graph import IntelligenceGraph
from core.event_manager import EventManager
from core.prediction_engine import PredictionEngine
from core.semantic_reasoner import SemanticReasoner
from db.models import Task, TaskStatus, Video, VideoStatus
from db.session import SessionLocal, init_db
from orchestrator.service import OrchestratorService

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    settings.videos_root_path.mkdir(parents=True, exist_ok=True)
    settings.audio_root_path.mkdir(parents=True, exist_ok=True)
    settings.frames_root_path.mkdir(parents=True, exist_ok=True)


def _runtime_snapshot(db: Session) -> dict:
    redis_status = "ok"
    redis_error = None
    queue_depths: dict[str, int] = {}
    try:
        redis_client = get_redis()
        redis_client.ping()
        queue_names = [
            settings.preprocessing_queue_name,
            settings.audio_queue_name,
            settings.person_queue_name,
            "queue:deterministic_replay",
            "queue:system_alerts",
        ]
        for queue_name in queue_names:
            queue_depths[queue_name] = int(redis_client.llen(queue_name))
    except RedisConnectionError as exc:
        redis_status = "degraded"
        redis_error = str(exc)

    db_status = "ok"
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - runtime safeguard
        db_status = "degraded"
        db_error = str(exc)

    return {
        "api": "ok",
        "redis": {"status": redis_status, "error": redis_error, "queues": queue_depths},
        "database": {"status": db_status, "url": settings.database_url, "error": db_error},
    }


@app.get("/")
def root() -> dict:
    return {"service": settings.app_name, "status": "ok"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    return _runtime_snapshot(db)


class StartAnalysisRequest(BaseModel):
    video_id: str
    modes: dict[str, bool] = {}


def _event(event_type: str, video_id: str, ts: float, confidence: float, source: str, payload: dict) -> dict:
    return {
        "event_id": f"{video_id}:{event_type}:{uuid4().hex[:10]}",
        "job_id": video_id,
        "event_type": event_type,
        "timestamp_sec": ts,
        "confidence": confidence,
        "source": source,
        "payload": payload,
    }


def _run_synthetic_pipeline(db: Session, video: Video, modes: dict[str, bool]) -> dict:
    event_manager = EventManager(db=db)
    enabled = {
        "face": bool(modes.get("face", False)),
        "person": bool(modes.get("person", True)),
        "object": bool(modes.get("object", False)),
        "audio": bool(modes.get("audio", True)),
    }
    if all(enabled.values()):
        enabled["full"] = True

    video.status = VideoStatus.processing
    video.metadata_json = {**video.metadata_json, "analysis_modes": enabled}
    db.flush()

    tasks = db.execute(select(Task).where(Task.video_id == video.id)).scalars().all()
    for task in tasks:
        task.status = TaskStatus.running
        task.error_message = None
    db.flush()

    t = 0.5
    events: list[dict] = []
    events.append(_event("pipeline_started", video.id, t, 1.0, "orchestrator", {"modes": enabled}))
    t += 0.3
    events.append(_event("preprocessing_completed", video.id, t, 1.0, "preprocessing", {"frames": 24, "fps": 2}))

    if enabled["audio"]:
        t += 0.4
        events.append(
            _event(
                "speech_segment",
                video.id,
                t,
                0.92,
                "audio.whisper",
                {"text": "User entered scene and started discussion", "start_sec": t - 0.2, "end_sec": t + 1.4},
            )
        )

    if enabled["person"]:
        t += 0.5
        events.append(
            _event(
                "person_track_start",
                video.id,
                t,
                0.93,
                "person.yolo",
                {"track_id": "track-1", "bbox": [0.12, 0.2, 0.22, 0.46]},
            )
        )
        t += 0.3
        events.append(
            _event(
                "person_detected",
                video.id,
                t,
                0.95,
                "person.yolo",
                {"track_id": "track-1", "bbox": [0.15, 0.21, 0.22, 0.46]},
            )
        )

    if enabled["object"]:
        t += 0.4
        events.append(
            _event(
                "object_detected",
                video.id,
                t,
                0.88,
                "object.detector",
                {"label": "product_box", "bbox": [0.55, 0.35, 0.2, 0.2]},
            )
        )

    if enabled["face"]:
        t += 0.4
        events.append(
            _event(
                "face_detected",
                video.id,
                t,
                0.83,
                "face.recognizer",
                {"identity": "person_A", "track_id": "track-1"},
            )
        )

    for ev in events:
        event_manager.create_event(ev)

    raw_events = event_manager.query_events(video.id)
    enriched = EventEnricher().enrich(job_id=video.id, raw_events=raw_events)
    graph_state = IntelligenceGraph().build_or_update(job_id=video.id, enriched_events=enriched)
    semantic = SemanticReasoner(event_manager=event_manager, graph_query_engine=GraphQueryEngine())
    prediction = PredictionEngine(graph_query_engine=GraphQueryEngine(), semantic_reasoner=semantic)

    for task in tasks:
        task.status = TaskStatus.success
        task.result = {"analysis_modes": enabled}
        task.error_message = None
    video.status = VideoStatus.completed
    db.commit()

    return {
        "video_id": video.id,
        "modes": enabled,
        "event_count": len(raw_events),
        "graph_version": graph_state.graph_version,
        "semantic_scene": semantic.build_scene_understanding(video.id),
        "prediction_scene": prediction.predict_scene_evolution(video.id),
    }


@app.post("/start-analysis")
def start_analysis(payload: StartAnalysisRequest, db: Session = Depends(get_db)) -> dict:
    video = db.execute(select(Video).where(Video.id == payload.video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return _run_synthetic_pipeline(db=db, video=video, modes=payload.modes)


@app.post("/upload-video")
def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    orchestrator = OrchestratorService(db=db, redis_client=redis_client)
    result = orchestrator.handle_video_upload(file)
    return {"video_id": result["video_id"], "status": result["status"]}


@app.get("/videos/{video_id}")
def get_video_status(
    video_id: str,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    tasks = db.execute(select(Task).where(Task.video_id == video_id)).scalars().all()
    return {
        "video_id": video.id,
        "status": video.status.value,
        "metadata": video.metadata_json,
        "tasks": [{"task_id": t.id, "type": t.type, "status": t.status.value, "error": t.error_message} for t in tasks],
    }


@app.get("/videos/{video_id}/file")
def get_video_file(video_id: str, db: Session = Depends(get_db)) -> FileResponse:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(video.file_path, media_type="video/mp4", filename=video.original_filename)


@app.get("/videos/{video_id}/events")
def get_video_events(
    video_id: str,
    start: float | None = None,
    end: float | None = None,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    event_manager = EventManager(db=db)
    if start is None and end is None:
        events = event_manager.query_events(video_id)
    else:
        if start is None or end is None:
            raise HTTPException(status_code=400, detail="Both start and end must be provided for time range queries.")
        if start > end:
            raise HTTPException(status_code=400, detail="start must be less than or equal to end.")
        events = event_manager.query_events_by_time_range(video_id, start, end)

    return {"video_id": video_id, "events": [event.model_dump() for event in events]}


@app.get("/videos/{video_id}/events/enriched")
def get_enriched_video_events(
    video_id: str,
    start: float | None = None,
    end: float | None = None,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    event_manager = EventManager(db=db)
    enricher = EventEnricher()
    if start is None and end is None:
        events = event_manager.query_events(video_id)
    else:
        if start is None or end is None:
            raise HTTPException(status_code=400, detail="Both start and end must be provided for time range queries.")
        if start > end:
            raise HTTPException(status_code=400, detail="start must be less than or equal to end.")
        events = event_manager.query_events_by_time_range(video_id, start, end)

    enriched = enricher.enrich(job_id=video_id, raw_events=events)
    return {"video_id": video_id, "events": enriched}


@app.post("/videos/{video_id}/graph/rebuild")
def rebuild_intelligence_graph(
    video_id: str,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    event_manager = EventManager(db=db)
    enricher = EventEnricher()
    graph = IntelligenceGraph()
    raw_events = event_manager.query_events(video_id)
    enriched_events = enricher.enrich(job_id=video_id, raw_events=raw_events)
    state = graph.build_or_update(job_id=video_id, enriched_events=enriched_events)
    return {"video_id": video_id, "node_count": len(state.nodes), "edge_count": len(state.edges)}


@app.get("/videos/{video_id}/graph/person/{entity_id}/timeline")
def get_person_timeline(
    video_id: str,
    entity_id: str,
    start: float | None = None,
    end: float | None = None,
) -> dict:
    query_engine = GraphQueryEngine()
    return {
        "video_id": video_id,
        **query_engine.get_person_timeline(job_id=video_id, entity_id=entity_id, start_sec=start, end_sec=end),
    }


@app.get("/videos/{video_id}/graph/person/{entity_id}/speech")
def get_person_speech(
    video_id: str,
    entity_id: str,
    start: float | None = None,
    end: float | None = None,
) -> dict:
    query_engine = GraphQueryEngine()
    return {
        "video_id": video_id,
        "entity_id": entity_id,
        "speech": query_engine.get_speech_by_person(video_id, entity_id, start_sec=start, end_sec=end),
    }


@app.get("/videos/{video_id}/graph/person/{entity_id}/interactions")
def get_person_interactions(
    video_id: str,
    entity_id: str,
    start: float | None = None,
    end: float | None = None,
) -> dict:
    query_engine = GraphQueryEngine()
    return {
        "video_id": video_id,
        "entity_id": entity_id,
        "interactions": query_engine.get_interactions(video_id, entity_id, start_sec=start, end_sec=end),
    }


@app.get("/videos/{video_id}/semantic/scene")
def get_semantic_scene(
    video_id: str,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    reasoner = SemanticReasoner(event_manager=EventManager(db=db), graph_query_engine=GraphQueryEngine())
    return {"video_id": video_id, **reasoner.build_scene_understanding(video_id)}


@app.get("/videos/{video_id}/semantic/interactions")
def get_semantic_interactions(
    video_id: str,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    reasoner = SemanticReasoner(event_manager=EventManager(db=db), graph_query_engine=GraphQueryEngine())
    return {"video_id": video_id, "interactions": reasoner.build_interactions(video_id)}


@app.get("/videos/{video_id}/semantic/timeline")
def get_semantic_timeline(
    video_id: str,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    reasoner = SemanticReasoner(event_manager=EventManager(db=db), graph_query_engine=GraphQueryEngine())
    return {"video_id": video_id, "timeline": reasoner.build_narrative_timeline(video_id)}


def _build_prediction_engine(db: Session) -> PredictionEngine:
    event_manager = EventManager(db=db)
    graph_query_engine = GraphQueryEngine()
    semantic_reasoner = SemanticReasoner(event_manager=event_manager, graph_query_engine=graph_query_engine)
    return PredictionEngine(
        graph_query_engine=graph_query_engine,
        semantic_reasoner=semantic_reasoner,
    )


@app.get("/videos/{video_id}/prediction/actions")
def get_action_predictions(
    video_id: str,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    engine = _build_prediction_engine(db)
    return {"video_id": video_id, "predictions": engine.predict_actions(video_id)}


@app.get("/videos/{video_id}/prediction/interactions")
def get_interaction_predictions(
    video_id: str,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    engine = _build_prediction_engine(db)
    return {"video_id": video_id, "predictions": engine.predict_interactions(video_id)}


@app.get("/videos/{video_id}/prediction/scene")
def get_scene_predictions(
    video_id: str,
    db: Session = Depends(get_db),
) -> dict:
    video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    engine = _build_prediction_engine(db)
    return {"video_id": video_id, "prediction": engine.predict_scene_evolution(video_id)}
