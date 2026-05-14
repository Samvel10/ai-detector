import { useMemo } from "react";
import { useDashboardStore } from "../state/useDashboardStore";
import { EMPTY_PAYLOAD, useLiveStore } from "../state/useLiveStore";

export function TimelineIntelligenceView() {
  const activeFilters = useDashboardStore((s) => s.activeFilters);
  const timelinePayload = useLiveStore((s) => s.streams.timeline?.payload ?? EMPTY_PAYLOAD);
  const semanticPayload = useLiveStore((s) => s.streams.semantic?.payload ?? EMPTY_PAYLOAD);
  const rawEvents = timelinePayload.events;
  const rawSemanticTimeline = semanticPayload.timeline;
  const events = Array.isArray(rawEvents)
    ? (rawEvents as Array<{ event_id?: string; event_type?: string; timestamp_sec?: number; payload?: Record<string, unknown> }>)
    : [];
  const semanticTimeline = Array.isArray(rawSemanticTimeline)
    ? (rawSemanticTimeline as Array<{ summary_text?: string; time_range?: number[] }>)
    : [];

  const filtered = useMemo(() => {
    const list = events;
    if (activeFilters.length === 0) return list;
    return list.filter((e) => activeFilters.includes(String(e.event_type ?? "")));
  }, [events, activeFilters]);
  const maxTs = useMemo(
    () => filtered.reduce((max, item) => Math.max(max, Number(item.timestamp_sec ?? 0)), 1),
    [filtered]
  );
  const groupedSummary = useMemo(() => {
    const byType = new Map<string, { count: number; firstTs: number; lastTs: number }>();
    for (const event of events) {
      const type = String(event.event_type ?? "unknown");
      const ts = Number(event.timestamp_sec ?? 0);
      const prev = byType.get(type);
      if (!prev) {
        byType.set(type, { count: 1, firstTs: ts, lastTs: ts });
      } else {
        byType.set(type, {
          count: prev.count + 1,
          firstTs: Math.min(prev.firstTs, ts),
          lastTs: Math.max(prev.lastTs, ts),
        });
      }
    }
    return Array.from(byType.entries())
      .map(([eventType, stats]) => ({ eventType, ...stats }))
      .sort((a, b) => b.count - a.count || a.firstTs - b.firstTs);
  }, [events]);

  const eventTypeColors: Record<string, string> = {
    person_detected: "bg-lime-500/15 text-lime-300 border-lime-700/50",
    face_detected: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-700/50",
    object_detected: "bg-amber-500/15 text-amber-300 border-amber-700/50",
    action_detected: "bg-violet-500/15 text-violet-300 border-violet-700/50",
    speech_segment: "bg-sky-500/15 text-sky-300 border-sky-700/50",
    person_track_start: "bg-emerald-500/15 text-emerald-300 border-emerald-700/50",
    person_track_end: "bg-rose-500/15 text-rose-300 border-rose-700/50",
    frame_processed: "bg-slate-500/15 text-slate-300 border-slate-700/50",
    audio_extracted: "bg-slate-500/15 text-slate-300 border-slate-700/50",
  };

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900/95 to-slate-950/95 p-4 shadow-lg shadow-black/30">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-slate-100">Timeline Intelligence</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">Detected events grouped by type and time.</p>
      </div>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Detection summary</h3>
      <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
        {groupedSummary.slice(0, 8).map((item) => {
          const tint = eventTypeColors[item.eventType] ?? eventTypeColors.frame_processed;
          return (
            <div key={item.eventType} className={`rounded-lg border px-2.5 py-2 text-xs ${tint}`}>
              <p className="truncate font-medium">{item.eventType}</p>
              <p className="text-[11px] opacity-80">
                {item.count} · {item.firstTs.toFixed(1)}–{item.lastTs.toFixed(1)}s
              </p>
            </div>
          );
        })}
        {groupedSummary.length === 0 ? (
          <div className="rounded-lg bg-slate-800/60 px-3 py-2 text-xs text-slate-400">No detections yet.</div>
        ) : null}
      </div>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Events</h3>
      <div className="space-y-1.5">
        {filtered.slice(0, 20).map((event, idx) => {
          const type = String(event.event_type ?? "event");
          const tint = eventTypeColors[type] ?? eventTypeColors.frame_processed;
          return (
            <div
              key={event.event_id ?? `${type}-${idx}`}
              className="flex items-center gap-3 rounded-lg border border-slate-800/60 bg-slate-900/60 px-3 py-2 text-xs"
            >
              <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tint}`}>
                {type.replace(/_/g, " ")}
              </span>
              <div className="flex-1 min-w-0">
                {event.event_type === "speech_segment" && typeof event.payload?.text === "string" ? (
                  <p className="truncate text-slate-200">{event.payload.text}</p>
                ) : null}
                {event.event_type === "object_detected" && typeof event.payload?.label === "string" ? (
                  <p className="text-slate-300">{event.payload.label}</p>
                ) : null}
                {event.event_type === "action_detected" && typeof event.payload?.action === "string" ? (
                  <p className="text-slate-300">{event.payload.action}</p>
                ) : null}
                <div className="mt-1 h-1 rounded-full bg-slate-800/70">
                  <div
                    className="h-1 rounded-full bg-gradient-to-r from-sky-500 to-violet-500"
                    style={{ width: `${Math.max(2, (Number(event.timestamp_sec ?? 0) / maxTs) * 100)}%` }}
                  />
                </div>
              </div>
              <span className="mono shrink-0 text-[11px] text-slate-400">{Number(event.timestamp_sec ?? 0).toFixed(2)}s</span>
            </div>
          );
        })}
        {filtered.length === 0 ? (
          <div className="rounded-lg bg-slate-800/60 px-3 py-2 text-xs text-slate-400">No events match the current filters.</div>
        ) : null}
      </div>
      <h3 className="mt-4 mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Semantic narrative</h3>
      <div className="space-y-1.5">
        {semanticTimeline.slice(0, 10).map((segment, idx) => (
          <div key={idx} className="rounded-lg border border-slate-800/60 bg-slate-900/60 px-3 py-2 text-xs">
            <p className="text-slate-200">{segment.summary_text ?? "Unknown segment"}</p>
            <p className="text-[11px] text-slate-400">
              {Array.isArray(segment.time_range) && segment.time_range.length >= 2
                ? `${Number(segment.time_range[0] ?? 0).toFixed(2)}–${Number(segment.time_range[1] ?? 0).toFixed(2)}s`
                : "Time range unavailable"}
            </p>
          </div>
        ))}
        {semanticTimeline.length === 0 ? (
          <div className="rounded-lg bg-slate-800/60 px-3 py-2 text-xs text-slate-400">No semantic segments yet.</div>
        ) : null}
      </div>
    </div>
  );
}
