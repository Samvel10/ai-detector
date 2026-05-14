import { useQuery } from "@tanstack/react-query";
import { api, apiBase } from "../api/client";
import { useDashboardStore } from "../state/useDashboardStore";
import { useLiveStore } from "../state/useLiveStore";

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${
        ok ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]" : "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]"
      }`}
    />
  );
}

export function StatusBar() {
  const selectedVideo = useDashboardStore((s) => s.selectedVideo);
  const lastIds = useLiveStore((s) => s.lastIds);
  const wsConnected = Object.keys(lastIds).length > 0;
  const { data: status } = useQuery({
    queryKey: ["status"],
    queryFn: () => api.getStatus(),
    refetchInterval: 4000,
  });
  const { data: videoStatus } = useQuery({
    queryKey: ["video-status-bar", selectedVideo],
    queryFn: () => api.getVideo(selectedVideo),
    enabled: !!selectedVideo,
    refetchInterval: 3000,
  });

  const apiOk = !!status && status.api === "ok";
  const redisOk = !!status && status.redis.status === "ok";
  const dbOk = !!status && status.database.status === "ok";

  return (
    <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/70 backdrop-blur">
      <div className="mx-auto flex max-w-screen-2xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="relative h-9 w-9 rounded-xl bg-gradient-to-br from-sky-400 to-violet-500 shadow-lg shadow-sky-700/30">
            <span className="absolute inset-0 grid place-items-center text-xs font-black text-slate-950">VA</span>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-slate-100">Video Intelligence</h1>
            <p className="text-[11px] text-slate-500">{apiBase}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <div className="flex items-center gap-1.5 rounded-full border border-slate-800 bg-slate-900/70 px-2.5 py-1">
            <Dot ok={apiOk} /> API
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-slate-800 bg-slate-900/70 px-2.5 py-1">
            <Dot ok={redisOk} /> Redis
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-slate-800 bg-slate-900/70 px-2.5 py-1">
            <Dot ok={dbOk} /> SQLite
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-slate-800 bg-slate-900/70 px-2.5 py-1">
            <Dot ok={wsConnected} /> WS
          </div>
          {status ? (
            <div className="hidden md:flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-2.5 py-1 text-[11px]">
              <span className="text-slate-500">queues</span>
              <span className="text-slate-300">
                p:{status.redis.queues["queue:preprocessing"] ?? 0}·
                a:{status.redis.queues["queue:audio"] ?? 0}·
                pe:{status.redis.queues["queue:person"] ?? 0}
              </span>
            </div>
          ) : null}
        </div>

        <div className="flex items-center gap-2 text-xs">
          {selectedVideo ? (
            <div className="flex items-center gap-2 rounded-full border border-sky-700/60 bg-sky-500/10 px-3 py-1 text-sky-200">
              <span className="font-medium">video</span>
              <span className="font-mono text-[11px]">{selectedVideo.slice(0, 12)}…</span>
              {videoStatus ? <span className="rounded-full bg-sky-700/40 px-2 py-0.5 text-[10px]">{videoStatus.status}</span> : null}
            </div>
          ) : (
            <span className="rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1 text-slate-500">no video selected</span>
          )}
        </div>
      </div>
    </header>
  );
}
