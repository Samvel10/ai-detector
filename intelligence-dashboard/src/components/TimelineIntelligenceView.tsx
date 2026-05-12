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

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Timeline Intelligence View</h2>
      <h3 className="mb-2 text-xs font-semibold text-slate-300">Detected Summary</h3>
      <div className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        {groupedSummary.slice(0, 8).map((item) => (
          <div key={item.eventType} className="rounded border border-slate-700 bg-slate-800 p-2 text-xs">
            <p className="text-slate-100">{item.eventType}</p>
            <p className="text-slate-400">
              {item.count} detections | {item.firstTs.toFixed(2)}s - {item.lastTs.toFixed(2)}s
            </p>
          </div>
        ))}
        {groupedSummary.length === 0 ? (
          <div className="rounded bg-slate-800 p-2 text-xs text-slate-400">No detections yet.</div>
        ) : null}
      </div>
      <div className="space-y-2">
        {filtered.slice(0, 20).map((event, idx) => (
          <div key={event.event_id ?? `${event.event_type ?? "event"}-${idx}`} className="flex items-center justify-between rounded bg-slate-800 p-2 text-xs">
            <div className="w-9/12">
              <span>{event.event_type ?? "event"}</span>
              {event.event_type === "speech_segment" && typeof event.payload?.text === "string" ? (
                <p className="truncate text-[11px] text-slate-300">{event.payload.text}</p>
              ) : null}
              {event.event_type === "object_detected" && typeof event.payload?.label === "string" ? (
                <p className="text-[11px] text-slate-300">Object: {event.payload.label}</p>
              ) : null}
              {event.event_type === "action_detected" && typeof event.payload?.action === "string" ? (
                <p className="text-[11px] text-slate-300">Action: {event.payload.action}</p>
              ) : null}
              <div className="mt-1 h-1.5 rounded bg-slate-700">
                <div
                  className="h-1.5 rounded bg-blue-500"
                  style={{ width: `${Math.max(2, (Number(event.timestamp_sec ?? 0) / maxTs) * 100)}%` }}
                />
              </div>
            </div>
            <span>{Number(event.timestamp_sec ?? 0).toFixed(2)}s</span>
          </div>
        ))}
        {filtered.length === 0 ? (
          <div className="rounded bg-slate-800 p-2 text-xs text-slate-400">Loading timeline events...</div>
        ) : null}
      </div>
      <h3 className="mt-4 text-xs font-semibold text-slate-300">Semantic Segments</h3>
      <div className="mt-2 space-y-2">
        {semanticTimeline.slice(0, 10).map((segment, idx) => (
          <div key={idx} className="rounded bg-slate-800 p-2 text-xs">
            <p>{segment.summary_text ?? "Unknown segment"}</p>
            <p className="text-slate-400">
              {Array.isArray(segment.time_range) && segment.time_range.length >= 2
                ? `${Number(segment.time_range[0] ?? 0).toFixed(2)}s - ${Number(segment.time_range[1] ?? 0).toFixed(2)}s`
                : "Time range unavailable"}
            </p>
          </div>
        ))}
        {semanticTimeline.length === 0 ? (
          <div className="rounded bg-slate-800 p-2 text-xs text-slate-400">Loading semantic segments...</div>
        ) : null}
      </div>
    </div>
  );
}
