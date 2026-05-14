import { useEffect, useRef } from "react";
import Cytoscape from "cytoscape";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useDashboardStore } from "../state/useDashboardStore";
import { EMPTY_PAYLOAD, useLiveStore } from "../state/useLiveStore";

export function GraphExplorer() {
  const selectedVideo = useDashboardStore((s) => s.selectedVideo);
  const selectedEntity = useDashboardStore((s) => s.selectedEntity);
  const setSelectedEntity = useDashboardStore((s) => s.setSelectedEntity);
  const graphPayload = useLiveStore((s) => s.streams.graph?.payload ?? EMPTY_PAYLOAD);
  const ref = useRef<HTMLDivElement | null>(null);
  const { data } = useQuery({
    queryKey: ["graphTimeline", selectedVideo, selectedEntity],
    queryFn: () => api.getPersonTimeline(selectedVideo, selectedEntity),
    enabled: !!selectedVideo && !!selectedEntity,
  });
  const rebuild = useMutation({
    mutationFn: () => api.rebuildGraph(selectedVideo),
  });

  useEffect(() => {
    if (!ref.current) return;
    const edges = (data?.timeline ?? []).map((e) => ({
      data: { id: e.edge_id, source: e.from_node_id, target: e.to_node_id, label: e.edge_type },
    }));
    const nodes = Array.from(
      new Set(
        edges.flatMap((e) => [String(e.data.source), String(e.data.target)])
      )
    ).map((id) => ({ data: { id, label: id } }));

    const cy = Cytoscape({
      container: ref.current,
      elements: [...nodes, ...edges],
      style: [
        { selector: "node", style: { label: "data(label)", "background-color": "#2563eb", color: "#e2e8f0", "font-size": "8px" } },
        { selector: "edge", style: { label: "data(label)", width: 2, "line-color": "#94a3b8", color: "#cbd5e1", "font-size": "7px" } },
      ],
      layout: { name: "cose" },
    });
    cy.on("tap", "node", (evt) => setSelectedEntity(String(evt.target.id())));
    return () => cy.destroy();
  }, [data, setSelectedEntity]);

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900/95 to-slate-950/95 p-4 shadow-lg shadow-black/30">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">Graph Explorer</h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Live graph: {(graphPayload.node_count as number | undefined) ?? "-"} nodes ·{" "}
            {(graphPayload.edge_count as number | undefined) ?? "-"} edges
          </p>
        </div>
        <button
          disabled={!selectedVideo || rebuild.isPending}
          onClick={() => rebuild.mutate()}
          className="rounded-md border border-slate-700 bg-slate-800/70 px-2.5 py-1 text-[11px] text-slate-200 hover:border-sky-600 hover:text-sky-300 disabled:opacity-40"
        >
          {rebuild.isPending ? "rebuilding…" : "rebuild graph"}
        </button>
      </div>
      {!selectedEntity ? (
        <p className="mb-2 text-xs text-slate-500">Pick an entity ID (e.g. <span className="font-mono">person:p-1</span>) to render its lifecycle.</p>
      ) : !data?.timeline?.length ? (
        <p className="mb-2 text-xs text-slate-500">No graph timeline for this entity yet.</p>
      ) : null}
      <div ref={ref} className="h-64 w-full rounded-lg border border-slate-800 bg-slate-950/80" />
    </div>
  );
}
