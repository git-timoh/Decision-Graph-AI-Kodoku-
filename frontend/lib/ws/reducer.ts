/** Pure reducer: fold one WsEvent into graph state. One case per event type
 * from the design spec (section 7). Events arrive in id order, so we also
 * track the high-water mark for replay-on-reconnect. */
import type { GraphNode, GraphState, WsEvent } from "@/lib/ws/types";

function patchNode(
  state: GraphState,
  id: string,
  patch: Partial<GraphNode>,
): GraphState {
  const existing = state.nodes[id];
  if (!existing) return state;
  return { ...state, nodes: { ...state.nodes, [id]: { ...existing, ...patch } } };
}

export function reduce(state: GraphState, event: WsEvent): GraphState {
  // Ignore replays we've already folded in (idempotent on reconnect).
  if (event.id <= state.lastSeenEventId && event.id !== 0) return state;
  const p = event.payload as Record<string, never>;
  let next = state;

  switch (event.type) {
    case "session.started":
      next = { ...state, status: "running" };
      break;
    case "session.done":
      next = { ...state, status: "done" };
      break;
    case "session.error":
      next = { ...state, status: "error" };
      break;
    case "node.created": {
      const node = event.payload as unknown as GraphNode;
      next = { ...state, nodes: { ...state.nodes, [node.id]: node } };
      break;
    }
    case "node.updated":
    case "node.pruned": {
      const { id, ...rest } = event.payload as { id: string };
      const status = event.type === "node.pruned" ? { status: "pruned" as const } : {};
      next = patchNode(state, id, { ...(rest as Partial<GraphNode>), ...status });
      break;
    }
    case "evaluation.completed": {
      const { node_id, score, critique, dimensions } = event.payload as unknown as {
        node_id: string;
        score: number;
        critique: string;
        dimensions: Record<string, number>;
      };
      next = patchNode(state, node_id, { score, critique, dimensions });
      break;
    }
    case "checkpoint.reached":
      next = { ...state, status: "awaiting_human", checkpoint: event.payload as never };
      break;
    case "checkpoint.resolved":
      next = { ...state, status: "running", checkpoint: null };
      break;
    case "synthesis.streaming":
      next = { ...state, synthesis: state.synthesis + String((p as { delta?: string }).delta ?? "") };
      break;
    case "synthesis.completed":
      next = { ...state, synthesis: String((p as { text?: string }).text ?? state.synthesis) };
      break;
    case "cost.updated": {
      const { cost_usd, budget_usd } = event.payload as unknown as {
        cost_usd: number;
        budget_usd: number | null;
      };
      next = { ...state, costUsd: cost_usd, budgetUsd: budget_usd };
      break;
    }
    case "budget.exceeded": {
      const { cost_usd } = event.payload as unknown as { cost_usd: number };
      next = { ...state, status: "paused", costUsd: cost_usd, budgetExceeded: true };
      break;
    }
    default:
      next = state;
  }

  return { ...next, lastSeenEventId: Math.max(state.lastSeenEventId, event.id) };
}
