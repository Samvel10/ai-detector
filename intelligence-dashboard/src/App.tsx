import { ControlPanel } from "./components/ControlPanel";
import { GraphExplorer } from "./components/GraphExplorer";
import { PersonTrackingView } from "./components/PersonTrackingView";
import { PredictionPanel } from "./components/PredictionPanel";
import { SemanticPanel } from "./components/SemanticPanel";
import { StatusBar } from "./components/StatusBar";
import { TimelineIntelligenceView } from "./components/TimelineIntelligenceView";
import { VideoIntelligencePanel } from "./components/VideoIntelligencePanel";
import { VideoLibrary } from "./components/VideoLibrary";
import { useRealtimeVideo } from "./hooks/useRealtimeVideo";
import { useDashboardStore } from "./state/useDashboardStore";

export default function App() {
  useRealtimeVideo();
  const selectedVideo = useDashboardStore((s) => s.selectedVideo);

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,rgba(56,189,248,0.06),transparent_50%),radial-gradient(ellipse_at_bottom_right,rgba(139,92,246,0.05),transparent_50%)] text-slate-100">
      <StatusBar />

      <main className="mx-auto max-w-screen-2xl px-4 py-4">
        {!selectedVideo ? (
          <div className="mb-4 rounded-xl border border-amber-700/50 bg-gradient-to-r from-amber-500/10 to-transparent px-4 py-3 text-xs text-amber-200">
            Select a video from the library on the left, or upload a new one from the Analysis Control panel below it.
          </div>
        ) : null}
        <div className="grid grid-cols-12 gap-4">
          <aside className="col-span-12 space-y-4 lg:col-span-3">
            <VideoLibrary />
            <ControlPanel />
          </aside>
          <section className="col-span-12 space-y-4 lg:col-span-6">
            <VideoIntelligencePanel />
            <TimelineIntelligenceView />
            <GraphExplorer />
          </section>
          <section className="col-span-12 space-y-4 lg:col-span-3">
            <PersonTrackingView />
            <SemanticPanel />
            <PredictionPanel />
          </section>
        </div>
      </main>

      <footer className="border-t border-slate-800/80 bg-slate-950/70 px-4 py-3 text-center text-[11px] text-slate-500">
        Video Analysis Pipeline · FastAPI · Redis · Whisper · YOLO + ByteTrack · InsightFace · R3D
      </footer>
    </div>
  );
}
