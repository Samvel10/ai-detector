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

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Prediction Panel</h2>
      <div className="rounded border border-slate-700 bg-slate-800 p-2 text-xs">
        <p className="text-slate-200">Scene transition: {scenePred.likely_scene_transition ?? "-"}</p>
        <p className="text-slate-400">Confidence: {scenePred.confidence?.toFixed(2) ?? "-"}</p>
      </div>
      <h3 className="mt-3 text-xs font-semibold text-slate-300">Action Predictions</h3>
      <div className="mt-2 space-y-2">
        {effectiveActionCards.map((item, idx) => (
          <div key={idx} className="rounded border border-slate-700 bg-slate-800 p-2 text-xs">
            <p className="text-slate-100">{item.action}</p>
            <p className="text-slate-400">Probability: {item.probability.toFixed(2)}</p>
            <p className="text-slate-500">Window: {item.window}</p>
          </div>
        ))}
        {effectiveActionCards.length === 0 ? (
          <div className="rounded bg-slate-800 p-2 text-xs text-slate-400">Loading action predictions...</div>
        ) : null}
      </div>
      <h3 className="mt-3 text-xs font-semibold text-slate-300">Interaction Predictions</h3>
      <div className="mt-2 space-y-2">
        {interactionCards.map((item, idx) => (
          <div key={idx} className="rounded border border-slate-700 bg-slate-800 p-2 text-xs">
            <p className="text-slate-100">{item.interaction}</p>
            <p className="text-slate-400">Probability: {item.probability.toFixed(2)}</p>
            <p className="text-slate-500">Window: {item.window}</p>
          </div>
        ))}
        {interactionCards.length === 0 ? (
          <div className="rounded bg-slate-800 p-2 text-xs text-slate-400">Loading interaction predictions...</div>
        ) : null}
      </div>
    </div>
  );
}
