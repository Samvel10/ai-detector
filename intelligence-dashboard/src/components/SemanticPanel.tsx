import { EMPTY_PAYLOAD, useLiveStore } from "../state/useLiveStore";

export function SemanticPanel() {
  const semanticPayload = useLiveStore((s) => s.streams.semantic?.payload ?? EMPTY_PAYLOAD);
  const timelinePayload = useLiveStore((s) => s.streams.timeline?.payload ?? EMPTY_PAYLOAD);
  const rawScene = semanticPayload.scene;
  const rawInteractions = semanticPayload.interactions;
  const rawTimelineEvents = timelinePayload.events;
  const scene =
    ((rawScene && typeof rawScene === "object")
      ? (rawScene as { scene_type?: string; dominant_activity?: string; participants?: string[] })
      : {}) ?? {};
  const interactions: Array<{
    source_entity?: string;
    target_entity?: string;
    interaction_type?: string;
    confidence?: number;
  }> = Array.isArray(rawInteractions)
    ? (rawInteractions as Array<{ source_entity?: string; target_entity?: string; interaction_type?: string; confidence?: number }>)
    : [];
  const participants = Array.isArray(scene.participants) ? scene.participants : [];
  const timelineEvents = Array.isArray(rawTimelineEvents)
    ? (rawTimelineEvents as Array<{ event_type?: string; timestamp_sec?: number }>)
    : [];
  const speechCount = timelineEvents.filter((e) => e.event_type === "speech_segment").length;
  const personCount = timelineEvents.filter((e) => e.event_type === "person_detected").length;
  const objectCount = timelineEvents.filter((e) => e.event_type === "object_detected").length;
  const faceCount = timelineEvents.filter((e) => e.event_type === "face_detected").length;
  const actionCount = timelineEvents.filter((e) => e.event_type === "action_detected").length;
  const fallbackDominant =
    speechCount > 0 ? "talking" : personCount > 0 ? "people_present" : objectCount > 0 ? "object_observation" : "-";

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900/95 to-slate-950/95 p-4 shadow-lg shadow-black/30">
      <h2 className="text-sm font-semibold text-slate-100">Semantic Understanding</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">Scene-level meaning derived from raw events.</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-slate-500">scene</dt>
          <dd className="text-slate-100">{scene.scene_type ?? "-"}</dd>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-slate-500">dominant</dt>
          <dd className="text-slate-100">{scene.dominant_activity ?? fallbackDominant}</dd>
        </div>
        <div className="col-span-2 rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-slate-500">participants</dt>
          <dd className="text-slate-100">{participants.join(", ") || "—"}</dd>
        </div>
      </dl>
      <div className="mt-3 grid grid-cols-5 gap-1 text-center text-[10px]">
        {([
          ["person", personCount, "text-lime-300"],
          ["face", faceCount, "text-fuchsia-300"],
          ["object", objectCount, "text-amber-300"],
          ["speech", speechCount, "text-sky-300"],
          ["action", actionCount, "text-violet-300"],
        ] as const).map(([label, count, color]) => (
          <div key={label} className="rounded-md border border-slate-800 bg-slate-950/60 py-1.5">
            <div className={`mono text-sm font-semibold ${color}`}>{count}</div>
            <div className="text-slate-500">{label}</div>
          </div>
        ))}
      </div>
      <h3 className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Interactions</h3>
      <div className="mt-2 space-y-1.5">
        {interactions.slice(0, 10).map((i, idx) => (
          <div key={idx} className="rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-1.5 text-xs">
            <p className="truncate text-slate-200">
              <span className="mono text-sky-300">{i.source_entity ?? "-"}</span>
              <span className="mx-1 text-slate-500">→</span>
              <span className="mono text-fuchsia-300">{i.target_entity ?? "-"}</span>
            </p>
            <p className="text-[11px] text-slate-500">{i.interaction_type ?? "unknown"} · {Number(i.confidence ?? 0).toFixed(2)}</p>
          </div>
        ))}
        {interactions.length === 0 ? (
          <div className="rounded-lg bg-slate-800/60 px-2.5 py-2 text-xs text-slate-400">No semantic interactions inferred yet.</div>
        ) : null}
      </div>
    </div>
  );
}
