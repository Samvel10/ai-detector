type StreamType = "timeline" | "tracking" | "graph" | "semantic" | "prediction" | "system";

type ConnectArgs = {
  videoId: string;
  streams: StreamType[];
  lastIds: Record<string, string>;
  onEvent: (redisId: string, event: Record<string, unknown>) => void;
  onStatus?: (status: "connected" | "disconnected" | "reconnecting") => void;
};

const WS_BASE = (import.meta.env.VITE_WS_BASE as string | undefined) ?? "ws://localhost:8001";

export function connectVideoStream(args: ConnectArgs): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let retryMs = 1000;

  const connect = () => {
    if (closed) return;
    args.onStatus?.("reconnecting");
    ws = new WebSocket(`${WS_BASE}/ws`);
    ws.onopen = () => {
      retryMs = 1000;
      ws?.send(
        JSON.stringify({
          video_id: args.videoId,
          streams: args.streams,
          last_ids: args.lastIds,
        })
      );
      args.onStatus?.("connected");
    };
    ws.onmessage = (message) => {
      const data = JSON.parse(message.data);
      if (data.type !== "event") return;
      args.onEvent(String(data.id), data);
    };
    ws.onclose = () => {
      if (closed) return;
      args.onStatus?.("disconnected");
      setTimeout(connect, retryMs);
      retryMs = Math.min(10000, retryMs * 2);
    };
  };

  connect();
  return () => {
    closed = true;
    ws?.close();
  };
}
