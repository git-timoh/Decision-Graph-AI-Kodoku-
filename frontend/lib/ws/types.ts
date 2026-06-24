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
  dimensions?: Record<string, number>;
};

export type EngineStatus =
  | "draft"
  | "idle"
  | "running"
  | "awaiting_human"
  | "done"
  | "error"
  | "paused";

export type CheckpointCandidate = {
  id: string;
  title: string;
  content: string;
  score: number;
  critique: string;
  dimensions: Record<string, number>;
};

export type Checkpoint = {
  checkpoint_id: string;
  kind: string;
  payload: {
    proposed_keep: string[];
    proposed_prune: string[];
    candidates: CheckpointCandidate[];
  };
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
