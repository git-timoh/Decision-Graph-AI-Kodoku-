"use client";

import { create } from "zustand";

type SessionStore = {
  /** Counter that components mutate to trigger a re-fetch of the session list. */
  sidebarRefreshTick: number;
  refreshSidebar: () => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
  sidebarRefreshTick: 0,
  refreshSidebar: () =>
    set((state) => ({ sidebarRefreshTick: state.sidebarRefreshTick + 1 })),
}));
