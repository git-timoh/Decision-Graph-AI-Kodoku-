"use client";

import { create } from "zustand";

import { reduce } from "@/lib/ws/reducer";
import {
  emptyGraph,
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
  seedGraph: (nodes: GraphNode[]) => void;
  applyEvent: (event: WsEvent) => void;
  setConnected: (connected: boolean) => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
  sidebarRefreshTick: 0,
  refreshSidebar: () =>
    set((state) => ({ sidebarRefreshTick: state.sidebarRefreshTick + 1 })),

  graph: emptyGraph(),
  connected: false,
  seedGraph: (nodes) =>
    set(() => ({
      graph: {
        ...emptyGraph(),
        nodes: Object.fromEntries(nodes.map((n) => [n.id, n])),
      },
    })),
  applyEvent: (event) => set((state) => ({ graph: reduce(state.graph, event) })),
  setConnected: (connected) => set({ connected }),
}));
