/** Pure replay fold: graph state after the first `cursor` events.
 * Refolds from emptyGraph() (not incremental applyEvent) so stepping
 * backward works — applyEvent dedupes by lastSeenEventId. */
import { reduce } from "@/lib/ws/reducer";
import { emptyGraph, type GraphState, type WsEvent } from "@/lib/ws/types";

export function graphAtCursor(events: WsEvent[], cursor: number): GraphState {
  return events.slice(0, cursor).reduce(reduce, emptyGraph());
}
