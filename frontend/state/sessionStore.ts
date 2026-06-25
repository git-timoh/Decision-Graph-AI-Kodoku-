"use client";

import { create } from "zustand";

import { reduce } from "@/lib/ws/reducer";
import {
  emptyGraph,
  type EngineStatus,
  type GraphNode,
  type GraphState,
  type WsEvent,
} from "@/lib/ws/types";

type SessionStore = {
  /** Counter that components mutate to trigger a re-fetch of the session list. */
  sidebarRefreshTick: number;
  refreshSidebar: () => void;

  /** Live graph for the session currently open at /s/[id]. */
  graph: GraphState;
  connected: boolean;
  seedGraph: (
    nodes: GraphNode[],
    initial?: { status?: EngineStatus; synthesis?: string },
  ) => void;
  applyEvent: (event: WsEvent) => void;
  setGraph: (graph: GraphState) => void;
  setConnected: (connected: boolean) => void;

  /** Node currently shown in the NodeDrawer, if any. */
  selectedNodeId: string | null;
  selectNode: (id: string) => void;
  clearSelection: () => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
  sidebarRefreshTick: 0,
  refreshSidebar: () =>
    set((state) => ({ sidebarRefreshTick: state.sidebarRefreshTick + 1 })),

  graph: emptyGraph(),
  connected: false,
  seedGraph: (nodes, initial) =>
    set(() => ({
      graph: {
        ...emptyGraph(),
        ...initial,
        nodes: Object.fromEntries(nodes.map((n) => [n.id, n])),
      },
    })),
  applyEvent: (event) => set((state) => ({ graph: reduce(state.graph, event) })),
  setGraph: (graph) => set({ graph }),
  setConnected: (connected) => set({ connected }),

  selectedNodeId: null,
  selectNode: (id) => set({ selectedNodeId: id }),
  clearSelection: () => set({ selectedNodeId: null }),
}));
