import type {
  EventsResponse,
  GraphTimelineResponse,
  InteractionResponse,
  PredictionListResponse,
  PredictionSceneResponse,
  SceneResponse,
  TimelineResponse,
  VideoStatusResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit, retries = 2): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, init);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return (await response.json()) as T;
  } catch (error) {
    if (retries <= 0) throw error;
    return request<T>(path, init, retries - 1);
  }
}

export const api = {
  getVideo(videoId: string) {
    return request<VideoStatusResponse>(`/videos/${videoId}`);
  },
  getEvents(videoId: string) {
    return request<EventsResponse>(`/videos/${videoId}/events`);
  },
  getEnrichedEvents(videoId: string) {
    return request<EventsResponse>(`/videos/${videoId}/events/enriched`);
  },
  getScene(videoId: string) {
    return request<SceneResponse>(`/videos/${videoId}/semantic/scene`);
  },
  getSemanticInteractions(videoId: string) {
    return request<InteractionResponse>(`/videos/${videoId}/semantic/interactions`);
  },
  getSemanticTimeline(videoId: string) {
    return request<TimelineResponse>(`/videos/${videoId}/semantic/timeline`);
  },
  getPredictionActions(videoId: string) {
    return request<PredictionListResponse>(`/videos/${videoId}/prediction/actions`);
  },
  getPredictionInteractions(videoId: string) {
    return request<PredictionListResponse>(`/videos/${videoId}/prediction/interactions`);
  },
  getPredictionScene(videoId: string) {
    return request<PredictionSceneResponse>(`/videos/${videoId}/prediction/scene`);
  },
  rebuildGraph(videoId: string) {
    return request<{ video_id: string; node_count: number; edge_count: number }>(
      `/videos/${videoId}/graph/rebuild`,
      { method: "POST" }
    );
  },
  getPersonTimeline(videoId: string, entityId: string) {
    return request<GraphTimelineResponse>(`/videos/${videoId}/graph/person/${entityId}/timeline`);
  },
  getPersonInteractions(videoId: string, entityId: string) {
    return request<{ video_id: string; entity_id: string; interactions: Record<string, unknown>[] }>(
      `/videos/${videoId}/graph/person/${entityId}/interactions`
    );
  },
  startAnalysis(videoId: string, modes: Record<string, boolean>) {
    return request<{ video_id: string; event_count: number; modes: Record<string, boolean> }>("/start-analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: videoId, modes }),
    });
  },
};
