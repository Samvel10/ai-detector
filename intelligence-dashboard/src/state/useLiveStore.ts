import { create } from "zustand";

type StreamRecord = {
  sequence_id: number;
  version_hash: string;
  payload: Record<string, unknown>;
};

type LiveState = {
  streams: Record<string, StreamRecord>;
  lastIds: Record<string, string>;
  setStream: (streamType: string, record: StreamRecord, redisId: string) => void;
  hydrateBootstrap: (streamType: string, payload: Record<string, unknown>) => void;
  reset: () => void;
};

// Stable singleton used as a fallback for empty selectors. Returning a fresh `{}`
// from a Zustand v5 selector triggers an infinite render loop because
// `useSyncExternalStore` compares snapshots with `Object.is`, and a new object
// literal is never `Object.is`-equal to the previous one. Always reuse this
// reference instead of `?? {}`.
export const EMPTY_PAYLOAD: Record<string, unknown> = Object.freeze({});

export const useLiveStore = create<LiveState>((set) => ({
  streams: {},
  lastIds: {},
  setStream: (streamType, record, redisId) =>
    set((state) => ({
      streams: { ...state.streams, [streamType]: record },
      lastIds: { ...state.lastIds, [streamType]: redisId },
    })),
  hydrateBootstrap: (streamType, payload) =>
    set((state) => ({
      streams: {
        ...state.streams,
        [streamType]: {
          sequence_id: state.streams[streamType]?.sequence_id ?? 0,
          version_hash: state.streams[streamType]?.version_hash ?? "bootstrap",
          payload,
        },
      },
    })),
  reset: () => set({ streams: {}, lastIds: {} }),
}));
