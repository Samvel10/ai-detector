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
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Semantic Understanding</h2>
      <p className="text-xs">Scene: <span className="text-slate-300">{scene.scene_type ?? "-"}</span></p>
      <p className="text-xs">Dominant: <span className="text-slate-300">{scene.dominant_activity ?? fallbackDominant}</span></p>
      <p className="text-xs">Participants: <span className="text-slate-300">{participants.join(", ") || "-"}</span></p>
      <p className="mt-2 text-xs text-slate-400">
        Quick read: {personCount} person, {faceCount} face, {objectCount} object, {speechCount} speech, {actionCount} action events.
      </p>
      <h3 className="mt-3 text-xs font-semibold text-slate-300">Interactions</h3>
      <div className="mt-2 space-y-2">
        {interactions.slice(0, 10).map((i, idx) => (
          <div key={idx} className="rounded border border-slate-700 bg-slate-800 p-2 text-xs">
            <p className="text-slate-200">{i.source_entity ?? "-"} {'>'} {i.target_entity ?? "-"}</p>
            <p className="text-slate-400">{i.interaction_type ?? "unknown"} ({Number(i.confidence ?? 0).toFixed(2)})</p>
          </div>
        ))}
        {interactions.length === 0 ? (
          <div className="rounded bg-slate-800 p-2 text-xs text-slate-400">Loading semantic interactions...</div>
        ) : null}
      </div>
    </div>
  );
}
