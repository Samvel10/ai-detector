import { useMemo, useState } from "react";
import { useDashboardStore } from "../state/useDashboardStore";
import { api, apiBase } from "../api/client";

export function ControlPanel() {
  const setSelectedVideoUrl = useDashboardStore((s) => s.setSelectedVideoUrl);
  const selectedEntity = useDashboardStore((s) => s.selectedEntity);
  const graphViewMode = useDashboardStore((s) => s.graphViewMode);
  const activeFilters = useDashboardStore((s) => s.activeFilters);
  const setSelectedVideo = useDashboardStore((s) => s.setSelectedVideo);
  const setSelectedEntity = useDashboardStore((s) => s.setSelectedEntity);
  const setGraphViewMode = useDashboardStore((s) => s.setGraphViewMode);
  const toggleFilter = useDashboardStore((s) => s.toggleFilter);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploading, setUploading] = useState(false);
  const [statusText, setStatusText] = useState("Ready");
  const [modes, setModes] = useState({
    face: false,
    person: true,
    object: false,
    audio: true,
  });

  const fullMode = useMemo(
    () => modes.face && modes.person && modes.object && modes.audio,
    [modes]
  );

  const setMode = (key: keyof typeof modes, value: boolean) => {
    setModes((prev) => ({ ...prev, [key]: value }));
  };

  const setAllModes = (value: boolean) => {
    setModes({ face: value, person: value, object: value, audio: value });
  };

  const selectFile = (nextFile: File | null) => {
    if (!nextFile) return;
    setFile(nextFile);
    const objectUrl = URL.createObjectURL(nextFile);
    setPreviewUrl(objectUrl);
    setSelectedVideoUrl(objectUrl);
    setStatusText(`Selected ${nextFile.name}`);
  };

  const uploadVideo = async () => {
    if (!file) {
      setStatusText("Select a video file first.");
      return;
    }
    setUploading(true);
    setUploadProgress(0);
    setStatusText("Uploading video...");
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await new Promise<{ video_id: string; status: string }>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${apiBase}/upload-video`);
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            setUploadProgress(Math.round((event.loaded / event.total) * 100));
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText));
          } else {
            reject(new Error(`Upload failed: HTTP ${xhr.status}`));
          }
        };
        xhr.onerror = () => reject(new Error("Upload failed: network error"));
        xhr.send(form);
      });

      setSelectedVideo(response.video_id);
      setSelectedVideoUrl(`${apiBase}/videos/${response.video_id}/file`);
      setStatusText(`Video uploaded. id=${response.video_id}. Real pipeline queued.`);
      await api.rebuildGraph(response.video_id);
      setStatusText(`Real analysis queued and graph rebuild requested for ${response.video_id}`);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4 rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900/95 to-slate-950/95 p-4 shadow-lg shadow-black/30">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">Analysis Control</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">Upload a video and trigger the real pipeline.</p>
      </div>
      <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 p-3">
        <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">Video Input</p>
        <label className="flex cursor-pointer items-center justify-center rounded-lg border-2 border-dashed border-slate-700 p-4 text-xs text-slate-300 transition-colors hover:border-sky-500 hover:bg-sky-500/5">
          <span className="flex flex-col items-center gap-1">
            <span className="text-base">⬆️</span>
            <span>Drag a video here or click to pick</span>
          </span>
          <input
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => selectFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {previewUrl ? (
          <video className="mt-3 aspect-video w-full rounded-lg bg-black object-contain" src={previewUrl} controls />
        ) : null}
        <div className="mt-3 h-1.5 w-full rounded-full bg-slate-800/80">
          <div className="h-1.5 rounded-full bg-gradient-to-r from-sky-500 to-violet-500 transition-all" style={{ width: `${uploadProgress}%` }} />
        </div>
        <p className="mt-1 text-[11px] text-slate-400">{statusText}</p>
      </div>

      <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 p-3">
        <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">Analysis Modes (synthetic /start-analysis)</p>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {([
            ["face", "Face Recognition"],
            ["person", "Person Tracking"],
            ["object", "Object Detection"],
            ["audio", "Audio (Whisper)"],
          ] as const).map(([key, label]) => (
            <label
              key={key}
              className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2 py-2 transition-colors ${
                modes[key]
                  ? "border-sky-700/60 bg-sky-500/10 text-sky-200"
                  : "border-slate-800 bg-slate-900/60 text-slate-300 hover:border-slate-700"
              }`}
            >
              <input
                type="checkbox"
                className="accent-sky-500"
                checked={modes[key]}
                onChange={(e) => setMode(key, e.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>
        <label
          className={`mt-2 flex cursor-pointer items-center gap-2 rounded-lg border px-2 py-2 text-xs transition-colors ${
            fullMode
              ? "border-violet-700/70 bg-violet-500/10 text-violet-200"
              : "border-slate-800 bg-slate-900/60 text-slate-300"
          }`}
        >
          <input type="checkbox" className="accent-violet-500" checked={fullMode} onChange={(e) => setAllModes(e.target.checked)} />
          FULL MODE (all enabled)
        </label>
      </div>

      <button
        onClick={uploadVideo}
        disabled={uploading || !file}
        className="w-full rounded-lg bg-gradient-to-r from-sky-500 to-violet-500 px-3 py-2.5 text-sm font-semibold text-white shadow-lg shadow-sky-900/30 transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:bg-none disabled:opacity-50 disabled:shadow-none"
      >
        {uploading ? "Uploading…" : file ? "Upload & Start Analysis" : "Pick a video first"}
      </button>

      <div className="grid grid-cols-1 gap-2">
        <div>
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-slate-500">Entity ID (optional)</label>
          <input
            className="w-full rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-sky-600"
            value={selectedEntity}
            onChange={(e) => setSelectedEntity(e.target.value)}
            placeholder="person:..., audio_speaker:..."
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-slate-500">Graph View</label>
          <select
            className="w-full rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-sky-600"
            value={graphViewMode}
            onChange={(e) => setGraphViewMode(e.target.value as "force" | "timeline")}
          >
            <option value="force">Force</option>
            <option value="timeline">Timeline</option>
          </select>
        </div>
      </div>

      <div>
        <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">Event filters</p>
        <div className="flex flex-wrap gap-1.5">
          {[
            "speech_segment",
            "person_detected",
            "object_detected",
            "face_detected",
            "action_detected",
            "semantic",
            "prediction",
          ].map((filter) => (
            <button
              key={filter}
              onClick={() => toggleFilter(filter)}
              className={`rounded-full px-2.5 py-1 text-[11px] transition-colors ${
                activeFilters.includes(filter)
                  ? "bg-sky-500/20 text-sky-200 ring-1 ring-sky-600/60"
                  : "bg-slate-800/80 text-slate-400 hover:bg-slate-700/80"
              }`}
            >
              {filter}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
