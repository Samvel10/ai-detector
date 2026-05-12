import { useMemo, useState } from "react";
import { useDashboardStore } from "../state/useDashboardStore";
import { api } from "../api/client";

export function ControlPanel() {
  const selectedVideo = useDashboardStore((s) => s.selectedVideo);
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
        xhr.open("POST", "http://localhost:8000/upload-video");
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
      setSelectedVideoUrl(`http://localhost:8000/videos/${response.video_id}/file`);
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
    <div className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h2 className="text-sm font-semibold text-slate-200">Analysis Control</h2>
      <div className="rounded border border-slate-700 bg-slate-950 p-3">
        <p className="mb-2 text-xs text-slate-400">Video Input</p>
        <label className="flex cursor-pointer items-center justify-center rounded border border-dashed border-slate-600 p-3 text-xs text-slate-300 hover:border-blue-500">
          Drag and drop or click to pick video
          <input
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => selectFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {previewUrl ? (
          <video className="mt-3 aspect-video w-full rounded bg-black object-contain" src={previewUrl} controls />
        ) : null}
        <div className="mt-3 h-2 w-full rounded bg-slate-800">
          <div className="h-2 rounded bg-blue-500 transition-all" style={{ width: `${uploadProgress}%` }} />
        </div>
        <p className="mt-1 text-xs text-slate-400">{statusText}</p>
      </div>

      <div className="rounded border border-slate-700 bg-slate-950 p-3">
        <p className="mb-2 text-xs text-slate-400">Analysis Modes</p>
        <label className="mb-2 flex items-center gap-2 text-xs">
          <input type="checkbox" checked={modes.face} onChange={(e) => setMode("face", e.target.checked)} />
          Face Recognition
        </label>
        <label className="mb-2 flex items-center gap-2 text-xs">
          <input type="checkbox" checked={modes.person} onChange={(e) => setMode("person", e.target.checked)} />
          Person Tracking
        </label>
        <label className="mb-2 flex items-center gap-2 text-xs">
          <input type="checkbox" checked={modes.object} onChange={(e) => setMode("object", e.target.checked)} />
          Object/Product Detection
        </label>
        <label className="mb-2 flex items-center gap-2 text-xs">
          <input type="checkbox" checked={modes.audio} onChange={(e) => setMode("audio", e.target.checked)} />
          Audio Analysis (Whisper)
        </label>
        <label className="flex items-center gap-2 rounded bg-slate-800 px-2 py-1 text-xs text-blue-200">
          <input type="checkbox" checked={fullMode} onChange={(e) => setAllModes(e.target.checked)} />
          FULL MODE (all enabled)
        </label>
      </div>

      <button
        onClick={uploadVideo}
        disabled={uploading || !file}
        className="w-full rounded bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:bg-slate-700"
      >
        {uploading ? "Starting Analysis..." : "Start Analysis"}
      </button>
      <div>
        <label className="mb-1 block text-xs text-slate-400">Video ID</label>
        <input
          className="w-full rounded bg-slate-800 p-2 text-sm"
          value={selectedVideo}
          onChange={(e) => {
            const nextId = e.target.value.trim();
            setSelectedVideo(nextId);
            if (nextId) {
              setSelectedVideoUrl(`http://localhost:8000/videos/${nextId}/file`);
            }
          }}
          placeholder="Enter video_id"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs text-slate-400">Entity ID</label>
        <input
          className="w-full rounded bg-slate-800 p-2 text-sm"
          value={selectedEntity}
          onChange={(e) => setSelectedEntity(e.target.value)}
          placeholder="Optional entity_id"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs text-slate-400">Graph View</label>
        <select
          className="w-full rounded bg-slate-800 p-2 text-sm"
          value={graphViewMode}
          onChange={(e) => setGraphViewMode(e.target.value as "force" | "timeline")}
        >
          <option value="force">Force</option>
          <option value="timeline">Timeline</option>
        </select>
      </div>
      <div>
        <p className="mb-1 text-xs text-slate-400">Filters</p>
        {["speech_segment", "person_detected", "object_detected", "face_detected", "action_detected", "semantic", "prediction"].map((filter) => (
          <button
            key={filter}
            onClick={() => toggleFilter(filter)}
            className={`mr-2 mt-2 rounded px-2 py-1 text-xs ${
              activeFilters.includes(filter) ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-200"
            }`}
          >
            {filter}
          </button>
        ))}
      </div>
    </div>
  );
}
