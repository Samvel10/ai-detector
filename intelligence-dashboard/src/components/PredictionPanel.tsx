import { EMPTY_PAYLOAD, useLiveStore } from "../state/useLiveStore";

export function PredictionPanel() {
  const predictionPayload = useLiveStore((s) => s.streams.prediction?.payload ?? EMPTY_PAYLOAD);
  const timelinePayload = useLiveStore((s) => s.streams.timeline?.payload ?? EMPTY_PAYLOAD);
  const timelineEvents = Array.isArray(timelinePayload.events)
    ? (timelinePayload.events as Array<{ event_type?: string; payload?: Record<string, unknown> }>)
    : [];
  const actionPred = Array.isArray(predictionPayload.actions)
    ? (predictionPayload.actions as Array<Record<string, unknown>>)
    : [];
  const interactionPred = Array.isArray(predictionPayload.interactions)
    ? (predictionPayload.interactions as Array<Record<string, unknown>>)
    : [];
  const scenePred =
    ((predictionPayload.scene && typeof predictionPayload.scene === "object")
      ? (predictionPayload.scene as { likely_scene_transition?: string; confidence?: number })
      : {}) ?? {};
  const actionCards = actionPred.slice(0, 6).map((item) => ({
    action: String(item["action"] ?? item["predicted_action"] ?? "unknown"),
    probability: Number(item["probability"] ?? item["confidence"] ?? 0),
    window: String(item["time_window"] ?? item["window"] ?? "n/a"),
  }));
  const interactionCards = interactionPred.slice(0, 6).map((item) => ({
    interaction: String(item["interaction"] ?? item["interaction_type"] ?? "unknown"),
    probability: Number(item["probability"] ?? item["confidence"] ?? 0),
    window: String(item["time_window"] ?? item["window"] ?? "n/a"),
  }));
  const fallbackActionCards = timelineEvents
    .filter((e) => e.event_type === "action_detected")
    .slice(0, 6)
    .map((e) => ({
      action: String((e.payload ?? {})["action"] ?? "unknown"),
      probability: Number((e.payload ?? {})["confidence"] ?? 0.6),
      window: "detected_now",
    }));
  const effectiveActionCards = actionCards.length > 0 ? actionCards : fallbackActionCards;

  const renderBar = (value: number) => (
    <div className="mt-1.5 h-1 rounded-full bg-slate-800/70">
      <div
        className="h-1 rounded-full bg-gradient-to-r from-sky-500 to-violet-500"
        style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }}
      />
    </div>
  );

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900/95 to-slate-950/95 p-4 shadow-lg shadow-black/30">
      <h2 className="text-sm font-semibold text-slate-100">Predictions</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">Forward-looking guesses from the prediction engine.</p>
      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">scene transition</p>
        <p className="mt-0.5 text-slate-100">{scenePred.likely_scene_transition ?? "—"}</p>
        <p className="mt-0.5 text-[11px] text-slate-500">confidence {scenePred.confidence?.toFixed(2) ?? "-"}</p>
      </div>
      <h3 className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Action predictions</h3>
      <div className="mt-2 space-y-1.5">
        {effectiveActionCards.map((item, idx) => (
          <div key={idx} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs">
            <p className="text-slate-100">{item.action}</p>
            <p className="text-[11px] text-slate-500">p={item.probability.toFixed(2)} · {item.window}</p>
            {renderBar(item.probability)}
          </div>
        ))}
        {effectiveActionCards.length === 0 ? (
          <div className="rounded-lg bg-slate-800/60 px-2.5 py-2 text-xs text-slate-400">No action predictions yet.</div>
        ) : null}
      </div>
      <h3 className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Interaction predictions</h3>
      <div className="mt-2 space-y-1.5">
        {interactionCards.map((item, idx) => (
          <div key={idx} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs">
            <p className="text-slate-100">{item.interaction}</p>
            <p className="text-[11px] text-slate-500">p={item.probability.toFixed(2)} · {item.window}</p>
            {renderBar(item.probability)}
          </div>
        ))}
        {interactionCards.length === 0 ? (
          <div className="rounded-lg bg-slate-800/60 px-2.5 py-2 text-xs text-slate-400">No interaction predictions yet.</div>
        ) : null}
      </div>
    </div>
  );
}
