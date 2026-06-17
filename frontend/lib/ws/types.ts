/** Mirrors backend `WsEvent` (see backend/kodoku/api/dtos.py). Server-push only. */
export type WsEvent = {
  id: number;
  type: string;
  session_id: string;
  ts: string;
  payload: Record<string, unknown>;
};

export type GraphNode = {
  id: string;
  parent_id: string | null;
  depth: number;
  kind: "root" | "candidate" | "synthesis";
  title: string;
  content: string;
  status: "pending" | "active" | "pruned" | "kept" | "expanded";
  score?: number;
  critique?: string;
};

export type EngineStatus =
  | "idle"
  | "running"
  | "awaiting_human"
  | "done"
  | "error";

export type Checkpoint = {
  checkpoint_id: string;
  kind: string;
  payload: { prune: string[]; keep: string[]; expand: string[] };
};

export type GraphState = {
  nodes: Record<string, GraphNode>;
  status: EngineStatus;
  synthesis: string;
  checkpoint: Checkpoint | null;
  lastSeenEventId: number;
};

export function emptyGraph(): GraphState {
  return {
    nodes: {},
    status: "idle",
    synthesis: "",
    checkpoint: null,
    lastSeenEventId: 0,
  };
}
