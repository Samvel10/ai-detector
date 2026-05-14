import { useRef } from "react";
import { useDashboardStore } from "../state/useDashboardStore";
import { EMPTY_PAYLOAD, useLiveStore } from "../state/useLiveStore";

type TimelineEvent = {
  event_id?: string;
  event_type?: string;
  timestamp_sec?: number;
  confidence?: number;
  payload?: Record<string, unknown>;
};

type BoxOverlay = {
  key: string;
  label: string;
  tooltip: string;
  color: string;
  leftPct: number;
  topPct: number;
  widthPct: number;
  heightPct: number;
};

export function VideoIntelligencePanel() {
  const currentTime = useDashboardStore((s) => s.currentTime);
  const setCurrentTime = useDashboardStore((s) => s.setCurrentTime);
  const selectedVideoUrl = useDashboardStore((s) => s.selectedVideoUrl);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const timelinePayload = useLiveStore((s) => s.streams.timeline?.payload ?? EMPTY_PAYLOAD);
  const events = Array.isArray(timelinePayload.events)
    ? (timelinePayload.events as TimelineEvent[])
    : [];
  const overlays: BoxOverlay[] = events
    .filter((e) => {
      const type = String(e.event_type ?? "");
      if (!["person_detected", "object_detected", "face_detected"].includes(type)) return false;
      const ts = Number(e.timestamp_sec ?? 0);
      return Math.abs(ts - currentTime) <= 0.4;
    })
    .slice(0, 20)
    .map((event, idx) => {
      const payload = (event.payload ?? {}) as Record<string, unknown>;
      const bbox = Array.isArray(payload["bbox"]) ? (payload["bbox"] as number[]) : [];
      const frameW = Number(payload["frame_width"] ?? 0);
      const frameH = Number(payload["frame_height"] ?? 0);
      let leftPct = 5 + idx * 2;
      let topPct = 10 + idx * 2;
      let widthPct = 15;
      let heightPct = 25;
      if (bbox.length >= 4 && frameW > 0 && frameH > 0) {
        const [x1, y1, x2, y2] = bbox;
        leftPct = Math.max(0, Math.min(100, (Number(x1) / frameW) * 100));
        topPct = Math.max(0, Math.min(100, (Number(y1) / frameH) * 100));
        widthPct = Math.max(1, Math.min(100, ((Number(x2) - Number(x1)) / frameW) * 100));
        heightPct = Math.max(1, Math.min(100, ((Number(y2) - Number(y1)) / frameH) * 100));
      }
      const type = String(event.event_type ?? "event");
      const color =
        type === "person_detected" ? "border-lime-400 text-lime-300" : type === "face_detected" ? "border-fuchsia-400 text-fuchsia-300" : "border-amber-400 text-amber-300";
      const label =
        type === "person_detected"
          ? `Person ${(payload["track_id"] as string | undefined) ?? ""}`.trim()
          : type === "face_detected"
            ? `Face ${(payload["identity"] as string | undefined) ?? "unknown"}`
            : `Object ${(payload["label"] as string | undefined) ?? "detected"}`;
      const confidence = Number(event.confidence ?? payload["confidence"] ?? 0);
      const timestamp = Number(event.timestamp_sec ?? 0);
      return {
        key: String(event.event_id ?? `${type}-${idx}`),
        label,
        tooltip: `${label} | conf ${confidence.toFixed(2)} | t=${timestamp.toFixed(2)}s`,
        color,
        leftPct,
        topPct,
        widthPct,
        heightPct,
      };
    });
  const actionEvents = events
    .filter((e) => e.event_type === "action_detected")
    .map((e) => ({
      action: String(((e.payload ?? {}) as Record<string, unknown>)["action"] ?? "unknown"),
      ts: Number(e.timestamp_sec ?? 0),
      trackId: String(((e.payload ?? {}) as Record<string, unknown>)["track_id"] ?? "-"),
    }))
    .sort((a, b) => b.ts - a.ts)
    .slice(0, 3);

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900/95 to-slate-950/95 p-4 shadow-lg shadow-black/30">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">Video Player</h2>
          <p className="mt-0.5 text-[11px] text-slate-500">Overlay boxes track detections at the current frame.</p>
        </div>
        <span className="mono rounded-md border border-slate-700 bg-slate-900/80 px-2 py-1 text-[11px] text-slate-300">
          t = {currentTime.toFixed(2)}s
        </span>
      </div>
      <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-black">
        <video
          ref={videoRef}
          className="aspect-video h-full w-full bg-black object-contain"
          controls
          src={selectedVideoUrl || undefined}
          onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        />
        <div className="pointer-events-none absolute inset-0">
          {overlays.map((box) => (
            <div
              key={box.key}
              title={box.tooltip}
              className={`pointer-events-auto cursor-help absolute rounded-sm border-2 backdrop-blur-[1px] ${box.color}`}
              style={{ left: `${box.leftPct}%`, top: `${box.topPct}%`, width: `${box.widthPct}%`, height: `${box.heightPct}%` }}
            >
              <span className="absolute -top-5 left-0 rounded bg-black/80 px-1.5 py-0.5 text-[10px] font-medium">
                {box.label}
              </span>
            </div>
          ))}
        </div>
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(1, videoRef.current?.duration ?? 0)}
        value={currentTime}
        step={0.01}
        onChange={(e) => {
          const t = Number(e.target.value);
          setCurrentTime(t);
          if (videoRef.current) {
            videoRef.current.currentTime = t;
          }
        }}
        className="mt-3 w-full"
      />
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-slate-500">action insight</p>
          {actionEvents.length === 0 ? (
            <p className="mt-1 text-slate-400">No action recognized yet.</p>
          ) : (
            actionEvents.slice(0, 1).map((item, idx) => (
              <p key={`${item.trackId}-${idx}`} className="mt-1 text-slate-100">
                {item.action} <span className="text-slate-500">· {item.trackId} · {item.ts.toFixed(1)}s</span>
              </p>
            ))
          )}
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-slate-500">visible now</p>
          <p className="mt-1 text-slate-100">{overlays.length} detection{overlays.length === 1 ? "" : "s"}</p>
        </div>
      </div>
    </div>
  );
}
