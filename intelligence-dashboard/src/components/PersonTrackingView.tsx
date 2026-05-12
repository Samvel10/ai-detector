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
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Person Tracking View</h2>
      {!selectedEntity && <p className="text-xs text-slate-400">Select entity_id to inspect tracking timeline.</p>}
      <div className="space-y-2">
        {(data?.timeline ?? []).slice(0, 15).map((item) => (
          <div key={item.edge_id} className="rounded bg-slate-800 p-2 text-xs">
            <p>{item.edge_type}</p>
            <p className="text-slate-400">
              {Number(item.timestamp_sec ?? 0).toFixed(2)}s | conf {Number(item.confidence ?? 0).toFixed(2)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
