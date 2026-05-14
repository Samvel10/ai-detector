import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useDashboardStore } from "../state/useDashboardStore";

export function PersonTrackingView() {
  const selectedVideo = useDashboardStore((s) => s.selectedVideo);
  const selectedEntity = useDashboardStore((s) => s.selectedEntity);
  const { data } = useQuery({
    queryKey: ["personTimeline", selectedVideo, selectedEntity],
    queryFn: () => api.getPersonTimeline(selectedVideo, selectedEntity),
    enabled: !!selectedVideo && !!selectedEntity,
    refetchInterval: 4000,
  });

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900/95 to-slate-950/95 p-4 shadow-lg shadow-black/30">
      <h2 className="text-sm font-semibold text-slate-100">Entity Timeline</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        {selectedEntity ? `Lifecycle for ${selectedEntity}` : "Enter an entity ID to inspect."}
      </p>
      <div className="mt-3 space-y-1.5">
        {(data?.timeline ?? []).slice(0, 15).map((item) => (
          <div key={item.edge_id} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs">
            <p className="text-slate-100">{item.edge_type}</p>
            <p className="text-[11px] text-slate-500">
              t={Number(item.timestamp_sec ?? 0).toFixed(2)}s · conf {Number(item.confidence ?? 0).toFixed(2)}
            </p>
          </div>
        ))}
        {(!data || !data.timeline?.length) && selectedEntity ? (
          <div className="rounded-lg bg-slate-800/60 px-3 py-2 text-xs text-slate-400">No timeline data for this entity.</div>
        ) : null}
      </div>
    </div>
  );
}
