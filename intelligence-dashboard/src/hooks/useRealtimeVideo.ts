import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { connectVideoStream } from "../realtime/wsClient";
import { useDashboardStore } from "../state/useDashboardStore";
import { useLiveStore } from "../state/useLiveStore";

export function useRealtimeVideo() {
  const selectedVideo = useDashboardStore((s) => s.selectedVideo);
  const setStream = useLiveStore((s) => s.setStream);
  const hydrateBootstrap = useLiveStore((s) => s.hydrateBootstrap);
  const reset = useLiveStore((s) => s.reset);

  const { data: events } = useQuery({
    queryKey: ["bootstrap-events", selectedVideo],
    queryFn: () => api.getEvents(selectedVideo),
    enabled: !!selectedVideo,
  });
  const { data: enriched } = useQuery({
    queryKey: ["bootstrap-enriched", selectedVideo],
    queryFn: () => api.getEnrichedEvents(selectedVideo),
    enabled: !!selectedVideo,
  });
  const { data: scene } = useQuery({
    queryKey: ["bootstrap-scene", selectedVideo],
    queryFn: () => api.getScene(selectedVideo),
    enabled: !!selectedVideo,
  });
  const { data: predScene } = useQuery({
    queryKey: ["bootstrap-pred-scene", selectedVideo],
    queryFn: () => api.getPredictionScene(selectedVideo),
    enabled: !!selectedVideo,
  });
  const bootstrapHashesRef = useRef<Record<string, string>>({});

  useEffect(() => {
    if (!selectedVideo) {
      bootstrapHashesRef.current = {};
      reset();
      return;
    }
    const maybeHydrate = (streamType: string, payload: Record<string, unknown>) => {
      const nextHash = JSON.stringify(payload);
      if (bootstrapHashesRef.current[streamType] === nextHash) {
        return;
      }
      bootstrapHashesRef.current[streamType] = nextHash;
      hydrateBootstrap(streamType, payload);
    };

    if (events) maybeHydrate("timeline", { events: events.events });
    if (enriched) maybeHydrate("tracking", { events: enriched.events });
    if (scene) maybeHydrate("semantic", { scene });
    if (predScene) maybeHydrate("prediction", { scene: predScene.prediction });
  }, [selectedVideo, events, enriched, scene, predScene, hydrateBootstrap, reset]);

  useEffect(() => {
    if (!selectedVideo) return;
    // IMPORTANT:
    // Do not depend on live lastIds here. lastIds is updated on every incoming WS event,
    // and using it as an effect dependency causes reconnect loops and React update depth crashes.
    const initialLastIds = useLiveStore.getState().lastIds;
    return connectVideoStream({
      videoId: selectedVideo,
      streams: ["timeline", "tracking", "graph", "semantic", "prediction"],
      lastIds: initialLastIds,
      onEvent: (redisId, event) => {
        const streamType = String(event.stream_type);
        setStream(
          streamType,
          {
            sequence_id: Number(event.sequence_id ?? 0),
            version_hash: String(event.version_hash ?? ""),
            payload: (event.payload as Record<string, unknown>) ?? {},
          },
          redisId
        );
      },
    });
  }, [selectedVideo, setStream]);
}
