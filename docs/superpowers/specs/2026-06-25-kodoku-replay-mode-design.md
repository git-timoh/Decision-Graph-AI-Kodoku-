# Kodoku Replay Mode — Design Spec

**Date:** 2026-06-25
**Status:** Approved
**Phase:** Productize (replay mode)

## Goal

Let the user step through a session's history — watch the Tree-of-Thoughts graph
build, branch, get scored, prune, and synthesize — by scrubbing the durable
`events` journal. Frontend-only; no backend or schema change.

## Why it's cheap

Everything needed already exists:

- `GET /sessions/{id}/events?since=0` returns the full event list in `id` order.
- `reduce(state, event)` (`frontend/lib/ws/reducer.ts`) is a pure fold of one
  event into `GraphState`, already used by the live WS path.
- `emptyGraph()` (`frontend/lib/ws/types.ts`) is the fold's zero value.
- `Graph` / `NodeDrawer` render straight from `useSessionStore().graph`.

Replay = drive `store.graph` from a cursor over the fetched events instead of
from the live socket.

## Core mechanic

State at cursor `i` is a fresh refold:

```
graphAtCursor(events, i) = events.slice(0, i).reduce(reduce, emptyGraph())
```

Refolding from `emptyGraph()` (not incremental `applyEvent`) is what makes
**stepping backward** work: live `applyEvent` dedupes by `lastSeenEventId` and
would ignore lower ids. A fresh fold has no such guard issue because ids only
increase within a slice.

`cursor` ranges `[0, events.length]`. `0` = empty graph (before anything), `N` =
final state (equivalent to the live end state).

## Components

### 1. Store action — `setGraph(graph)`

`frontend/state/sessionStore.ts`. One setter so replay can push a whole folded
`GraphState`:

```ts
setGraph: (graph: GraphState) => set({ graph }),
```

(Type added to the `SessionStore` type. ~3 lines total.)

### 2. Pure helper — `graphAtCursor`

`frontend/lib/ws/replay.ts` (new):

```ts
export function graphAtCursor(events: WsEvent[], cursor: number): GraphState {
  return events.slice(0, cursor).reduce(reduce, emptyGraph());
}
```

Pure and isolated — the natural unit-test target if a runner is ever added.

### 3. `ReplayBar` component

`frontend/app/s/[sessionId]/ReplayBar.tsx` (new). Owns replay UI + clock:

- Local state: `events: WsEvent[]`, `cursor: number`, `playing: boolean`.
- On mount: `fetch(GET /events?since=0)` once; default `cursor = events.length`
  (show final state immediately), `playing = false`.
- Controls: a range slider (`0..events.length`), step-back / step-forward
  buttons (`cursor ± 1`, clamped), play/pause toggle.
- Play: `setInterval` advancing `cursor` by 1 at a fixed ~400ms; auto-pause at
  `events.length`.
- Effect: whenever `cursor` (or `events`) changes →
  `setGraph(graphAtCursor(events, cursor))`.
- Cleanup: clear the interval on unmount / pause.
- Empty events → render a muted "No events to replay" and no controls.

Fixed playback rate (no speed control — add only if asked).

`// ponytail:` refold from 0 each cursor move is O(n); memoize prefix states only
if event counts grow large enough to feel laggy.

### 4. `SessionGraphView` wiring

`frontend/app/s/[sessionId]/SessionGraphView.tsx`:

- New local boolean `replay`.
- Toolbar: a "Replay" toggle button (near the live/disconnected indicator).
- The existing connect effect gains `replay` in its deps and an early return:
  when `replay` is on, it does **not** call `connectSession` (and the prior
  cleanup has already disconnected the live socket). `ReplayBar` then owns the
  store via `setGraph`.
- When `replay` is on, render `<ReplayBar sessionId={...} />`; the live
  connection indicator is hidden/disabled in replay.
- Turning `replay` off re-runs the effect → reconnect live + reseed from props.

`Graph`, `NodeDrawer`, `CheckpointPanel`, synthesis panel are untouched — they
just reflect whatever `store.graph` holds.

## Out of scope / skipped (YAGNI)

- **Backend / schema** — none. Endpoint + reducer already exist.
- **Speed control** — fixed rate.
- **Prefix-state memoization** — refold each step; revisit only on lag.
- **Persisting replay position** — ephemeral component state.
- **Replay of checkpoint *interaction*** — replay shows `checkpoint.reached` as a
  state, it does not re-prompt the human (resolution events are in the journal
  and fold normally).

## Testing / verification

The frontend has **no test runner** (no vitest/jest, zero existing frontend
tests). Adding one for a single pure fold over the already-trusted `reduce` is
not worth a new dependency + config — skipped per YAGNI. `graphAtCursor` is a
thin `slice().reduce(reduce, emptyGraph())`; its correctness rides on `reduce`
and is caught immediately in manual smoke if wrong.

1. **Static:** `npm run lint` + `npm run typecheck` pass.
2. **Manual smoke (user):** open a finished session, toggle Replay, scrub +
   play/pause, confirm the graph builds/prunes and toggling back resumes live.
   (Dev server doesn't survive the agent env — owner verifies, per
   `kodoku-known-followups`.)

If a frontend test runner is later added, `graphAtCursor` is the natural first
unit (full fold at `cursor = events.length`, `emptyGraph()` at `0`).

## Files touched

- `frontend/state/sessionStore.ts` — add `setGraph`.
- `frontend/lib/ws/replay.ts` — new, `graphAtCursor`.
- `frontend/app/s/[sessionId]/ReplayBar.tsx` — new.
- `frontend/app/s/[sessionId]/SessionGraphView.tsx` — toggle + effect guard.
