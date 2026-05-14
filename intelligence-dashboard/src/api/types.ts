export type VideoStatusResponse = {
  video_id: string;
  status: string;
  metadata: Record<string, unknown>;
  tasks: { task_id: string; type: string; status: string; error: string | null }[];
};

export type VideoSummary = {
  video_id: string;
  original_filename: string;
  status: string;
  metadata: Record<string, unknown>;
  task_summary: Record<string, string>;
  created_at: string | null;
};

export type EventRecord = {
  event_id: string;
  job_id: string;
  event_type: string;
  timestamp_sec: number;
  confidence: number;
  source: string;
  payload: Record<string, unknown>;
};

export type EventsResponse = { video_id: string; events: EventRecord[] };

export type SceneResponse = {
  video_id: string;
  scene_type: string;
  participants: string[];
  dominant_activity: string;
  behavior_patterns: Record<string, unknown>[];
};

export type InteractionResponse = {
  video_id: string;
  interactions: {
    source_entity: string;
    target_entity: string;
    interaction_type: string;
    confidence: number;
    time_range: number[];
  }[];
};

export type TimelineResponse = {
  video_id: string;
  timeline: {
    summary_text: string;
    involved_entities: string[];
    time_range: number[];
    confidence: number;
  }[];
};

export type PredictionListResponse = {
  video_id: string;
  predictions: Record<string, unknown>[];
};

export type PredictionSceneResponse = {
  video_id: string;
  prediction: {
    scene_type_stability: number;
    likely_scene_transition: string;
    confidence: number;
    time_window: string;
  };
};

export type GraphTimelineResponse = {
  video_id: string;
  entity_id: string;
  lifecycle_state?: string;
  confidence_avg?: number;
  timeline: {
    edge_id: string;
    edge_type: string;
    from_node_id: string;
    to_node_id: string;
    timestamp_sec: number;
    confidence: number;
  }[];
};
