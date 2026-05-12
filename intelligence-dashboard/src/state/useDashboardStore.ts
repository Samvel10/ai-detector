import { create } from "zustand";

type DashboardState = {
  selectedVideo: string;
  selectedVideoUrl: string;
  selectedEntity: string;
  currentTime: number;
  graphViewMode: "force" | "timeline";
  activeFilters: string[];
  setSelectedVideo: (videoId: string) => void;
  setSelectedVideoUrl: (videoUrl: string) => void;
  setSelectedEntity: (entityId: string) => void;
  setCurrentTime: (time: number) => void;
  setGraphViewMode: (mode: "force" | "timeline") => void;
  toggleFilter: (filter: string) => void;
};

export const useDashboardStore = create<DashboardState>((set) => ({
  selectedVideo: "",
  selectedVideoUrl: "",
  selectedEntity: "",
  currentTime: 0,
  graphViewMode: "force",
  activeFilters: [],
  setSelectedVideo: (selectedVideo) => set({ selectedVideo }),
  setSelectedVideoUrl: (selectedVideoUrl) => set({ selectedVideoUrl }),
  setSelectedEntity: (selectedEntity) => set({ selectedEntity }),
  setCurrentTime: (currentTime) => set({ currentTime }),
  setGraphViewMode: (graphViewMode) => set({ graphViewMode }),
  toggleFilter: (filter) =>
    set((state) => ({
      activeFilters: state.activeFilters.includes(filter)
        ? state.activeFilters.filter((f) => f !== filter)
        : [...state.activeFilters, filter],
    })),
}));
