import { ControlPanel } from "./components/ControlPanel";
import { GraphExplorer } from "./components/GraphExplorer";
import { PersonTrackingView } from "./components/PersonTrackingView";
import { PredictionPanel } from "./components/PredictionPanel";
import { SemanticPanel } from "./components/SemanticPanel";
import { TimelineIntelligenceView } from "./components/TimelineIntelligenceView";
import { VideoIntelligencePanel } from "./components/VideoIntelligencePanel";
import { useRealtimeVideo } from "./hooks/useRealtimeVideo";
import { useDashboardStore } from "./state/useDashboardStore";

export default function App() {
  useRealtimeVideo();
  const selectedVideo = useDashboardStore((s) => s.selectedVideo);
  return (
    <div className="min-h-screen bg-slate-950 p-4 text-slate-100">
      {!selectedVideo ? (
        <div className="mb-4 rounded border border-amber-700 bg-amber-900/30 p-3 text-xs text-amber-200">
          No video selected. Dashboard is in standby mode and uses REST + WebSocket fallback once a video id is provided.
        </div>
      ) : null}
      <div className="grid grid-cols-12 gap-4">
        <aside className="col-span-12 lg:col-span-2">
          <ControlPanel />
        </aside>
        <main className="col-span-12 space-y-4 lg:col-span-7">
          <VideoIntelligencePanel />
          <TimelineIntelligenceView />
          <GraphExplorer />
        </main>
        <section className="col-span-12 space-y-4 lg:col-span-3">
          <PersonTrackingView />
          <SemanticPanel />
          <PredictionPanel />
        </section>
      </div>
    </div>
  );
}
