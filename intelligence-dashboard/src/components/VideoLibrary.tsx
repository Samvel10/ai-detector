import { useQuery } from "@tanstack/react-query";
import { api, apiBase } from "../api/client";
import type { VideoSummary } from "../api/types";
import { useDashboardStore } from "../state/useDashboardStore";

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-emerald-500/20 text-emerald-300 border-emerald-700/50",
  processing: "bg-sky-500/20 text-sky-300 border-sky-700/50",
  queued: "bg-amber-500/20 text-amber-300 border-amber-700/50",
  failed: "bg-rose-500/20 text-rose-300 border-rose-700/50",
  uploaded: "bg-slate-500/20 text-slate-300 border-slate-700/50",
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.uploaded;
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${style}`}>
      {status}
    </span>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export function VideoLibrary() {
  const selectedVideo = useDashboardStore((s) => s.selectedVideo);
  const setSelectedVideo = useDashboardStore((s) => s.setSelectedVideo);
  const setSelectedVideoUrl = useDashboardStore((s) => s.setSelectedVideoUrl);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["video-library"],
    queryFn: () => api.listVideos(50),
    refetchInterval: 5000,
  });

  const videos: VideoSummary[] = data?.videos ?? [];

  const selectVideo = (video: VideoSummary) => {
    setSelectedVideo(video.video_id);
    setSelectedVideoUrl(`${apiBase}/videos/${video.video_id}/file`);
  };

  return (
    <div className="space-y-3 rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900/95 to-slate-950/95 p-4 shadow-lg shadow-black/30">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">Video Library</h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {videos.length} video{videos.length === 1 ? "" : "s"} · click to inspect
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="rounded-md border border-slate-700 bg-slate-800/60 px-2 py-1 text-[11px] text-slate-300 hover:border-sky-600 hover:text-sky-300"
        >
          refresh
        </button>
      </div>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading videos…</p>
      ) : isError ? (
        <p className="text-xs text-rose-400">Cannot reach API at {apiBase}.</p>
      ) : videos.length === 0 ? (
        <p className="text-xs text-slate-500">No videos uploaded yet. Use the panel below to upload one.</p>
      ) : (
        <ul className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
          {videos.map((video) => {
            const isSelected = video.video_id === selectedVideo;
            return (
              <li key={video.video_id}>
                <button
                  onClick={() => selectVideo(video)}
                  className={`group w-full rounded-xl border px-3 py-2 text-left transition-all ${
                    isSelected
                      ? "border-sky-500/70 bg-sky-500/10 shadow-md shadow-sky-900/30"
                      : "border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-800/70"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="truncate text-xs font-medium text-slate-100">{video.original_filename}</span>
                    <StatusBadge status={video.status} />
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    {Object.entries(video.task_summary).map(([t, s]) => (
                      <span
                        key={t}
                        className={`rounded-md border px-1.5 py-0.5 text-[9px] uppercase tracking-wide ${
                          STATUS_STYLES[s] ?? STATUS_STYLES.uploaded
                        }`}
                        title={`${t} task ${s}`}
                      >
                        {t}·{s}
                      </span>
                    ))}
                  </div>
                  <p className="mt-1 truncate text-[10px] text-slate-500">
                    {video.video_id.slice(0, 8)}… · {formatDate(video.created_at)}
                  </p>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
