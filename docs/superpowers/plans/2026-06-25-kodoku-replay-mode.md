# Replay Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user scrub/step/play through a session's event journal and watch the graph rebuild, frontend-only.

**Architecture:** A cursor over the events fetched from the existing `GET /sessions/{id}/events?since=0`. State at cursor `i` is a fresh refold `events.slice(0,i).reduce(reduce, emptyGraph())` using the existing pure reducer, pushed into the Zustand store via a new `setGraph` action. A `ReplayBar` owns the cursor/clock UI; `SessionGraphView` toggles between live WS and replay.

**Tech Stack:** Next.js 14 (app router), React 18, Zustand, Tailwind, lucide-react. No backend change. No new dependency.

## Global Constraints

- **No new npm dependency.** Slider is native `<input type="range">`; icons from already-installed `lucide-react`.
- **No backend or schema change.** Reuse `GET /sessions/{id}/events?since=0` and `frontend/lib/ws/reducer.ts::reduce`.
- **No frontend test runner exists** (no vitest/jest). Per-task verification is `npm run typecheck` + `npm run lint` from `frontend/`. Behavior is smoke-tested by the user.
- **API base:** `process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"` (match existing files).
- All commands run from `frontend/`.

---

### Task 1: `setGraph` store action + `graphAtCursor` helper

Foundation: a way to push a whole folded graph into the store, and the pure fold-to-cursor function.

**Files:**
- Modify: `frontend/state/sessionStore.ts`
- Create: `frontend/lib/ws/replay.ts`

**Interfaces:**
- Consumes: `reduce` (`@/lib/ws/reducer`), `emptyGraph`, `GraphState`, `WsEvent` (`@/lib/ws/types`).
- Produces:
  - `useSessionStore().setGraph(graph: GraphState): void`
  - `graphAtCursor(events: WsEvent[], cursor: number): GraphState`

- [ ] **Step 1: Add `setGraph` to the store type**

In `frontend/state/sessionStore.ts`, in the `SessionStore` type, next to `applyEvent`:

```ts
  setGraph: (graph: GraphState) => void;
```

- [ ] **Step 2: Implement `setGraph` in the store**

In the `create<SessionStore>(...)` body, next to `applyEvent`:

```ts
  setGraph: (graph) => set({ graph }),
```

(`GraphState` is already imported in this file.)

- [ ] **Step 3: Create the `graphAtCursor` helper**

Create `frontend/lib/ws/replay.ts`:

```ts
/** Pure replay fold: graph state after the first `cursor` events.
 * Refolds from emptyGraph() (not incremental applyEvent) so stepping
 * backward works — applyEvent dedupes by lastSeenEventId. */
import { reduce } from "@/lib/ws/reducer";
import { emptyGraph, type GraphState, type WsEvent } from "@/lib/ws/types";

export function graphAtCursor(events: WsEvent[], cursor: number): GraphState {
  return events.slice(0, cursor).reduce(reduce, emptyGraph());
}
```

- [ ] **Step 4: Typecheck + lint**

Run: `npm run typecheck && npm run lint`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/state/sessionStore.ts frontend/lib/ws/replay.ts
git commit -m "feat(replay): setGraph store action + graphAtCursor fold"
```

---

### Task 2: `ReplayBar` component

The replay UI: fetches the journal once, owns cursor + play clock, drives the store.

**Files:**
- Create: `frontend/app/s/[sessionId]/ReplayBar.tsx`

**Interfaces:**
- Consumes: `graphAtCursor` (`@/lib/ws/replay`), `useSessionStore().setGraph`, `WsEvent` (`@/lib/ws/types`), `Button` (`@/components/ui/button`), icons from `lucide-react`.
- Produces: `ReplayBar({ sessionId }: { sessionId: string })` — default-rate (400ms) play/pause, step ±1, native range scrub.

- [ ] **Step 1: Create the component**

Create `frontend/app/s/[sessionId]/ReplayBar.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";

import { Button } from "@/components/ui/button";
import { graphAtCursor } from "@/lib/ws/replay";
import type { WsEvent } from "@/lib/ws/types";
import { useSessionStore } from "@/state/sessionStore";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const STEP_MS = 400;

export function ReplayBar({ sessionId }: { sessionId: string }) {
  const setGraph = useSessionStore((s) => s.setGraph);
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);

  // Fetch the full journal once.
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/sessions/${sessionId}/events?since=0`, {
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: WsEvent[]) => {
        if (cancelled) return;
        setEvents(rows);
        setCursor(rows.length); // start at the final state
      })
      .catch(() => {
        /* offline — leave events empty, bar shows the empty state */
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Drive the store from the cursor.
  // ponytail: refold from 0 each cursor move is O(n); memoize prefix states only if event counts grow large enough to lag.
  useEffect(() => {
    setGraph(graphAtCursor(events, cursor));
  }, [events, cursor, setGraph]);

  // Playback clock — advance one event per tick, auto-pause at the end.
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      setCursor((c) => {
        if (c >= events.length) {
          setPlaying(false);
          return c;
        }
        return c + 1;
      });
    }, STEP_MS);
    return () => clearInterval(t);
  }, [playing, events.length]);

  if (events.length === 0) {
    return (
      <div className="flex items-center border-t border-border px-6 py-3 text-xs text-muted-foreground">
        No events to replay.
      </div>
    );
  }

  const clamp = (n: number) => Math.max(0, Math.min(events.length, n));

  return (
    <div className="flex items-center gap-3 border-t border-border px-6 py-3">
      <Button
        size="sm"
        variant="outline"
        onClick={() => setCursor((c) => clamp(c - 1))}
        aria-label="Step back"
      >
        <SkipBack className="h-4 w-4" />
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setPlaying((p) => !p)}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setCursor((c) => clamp(c + 1))}
        aria-label="Step forward"
      >
        <SkipForward className="h-4 w-4" />
      </Button>
      <input
        type="range"
        min={0}
        max={events.length}
        value={cursor}
        onChange={(e) => {
          setPlaying(false);
          setCursor(clamp(Number(e.target.value)));
        }}
        className="flex-1"
        aria-label="Replay position"
      />
      <span className="text-xs text-muted-foreground tabular-nums">
        {cursor} / {events.length}
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + lint**

Run: `npm run typecheck && npm run lint`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/s/[sessionId]/ReplayBar.tsx
git commit -m "feat(replay): ReplayBar — scrub/step/play over the journal"
```

---

### Task 3: Wire replay toggle into `SessionGraphView`

Add the toggle, guard the live-connect effect, render `ReplayBar` in replay.

**Files:**
- Modify: `frontend/app/s/[sessionId]/SessionGraphView.tsx`

**Interfaces:**
- Consumes: `ReplayBar` (`./ReplayBar`).
- Produces: nothing new (UI behavior only).

- [ ] **Step 1: Import ReplayBar**

Add to the imports in `SessionGraphView.tsx` (next to the other local imports):

```tsx
import { ReplayBar } from "@/app/s/[sessionId]/ReplayBar";
```

- [ ] **Step 2: Add the `replay` state flag**

Inside the component, next to the other `useState` lines (e.g. after `const [emitting, setEmitting] = useState(false);`):

```tsx
  const [replay, setReplay] = useState(false);
```

- [ ] **Step 3: Guard the connect effect**

In the existing `useEffect` that seeds + connects, add an early return after `seedGraph(...)` and before `connectSession(...)`, and add `replay` to the dependency array. Replace the effect body's connect section so it reads:

```tsx
  useEffect(() => {
    seedGraph(seedNodes(initialNodes, initialEvaluations), {
      status: initialStatus,
      synthesis: initialSynthesis ?? "",
    });
    if (replay) return; // replay mode: ReplayBar drives the store, no live socket
    const disconnect = connectSession(sessionId, {
      apply: applyEvent,
      getSince: () => useSessionStore.getState().graph.lastSeenEventId,
      onConnected: setConnected,
    });
    return disconnect;
  }, [
    sessionId,
    initialStatus,
    initialSynthesis,
    initialNodes,
    initialEvaluations,
    seedGraph,
    applyEvent,
    setConnected,
    replay,
  ]);
```

- [ ] **Step 4: Hide the live indicator in replay + add the toggle button**

Replace the connection-indicator span:

```tsx
        <span className="text-xs text-muted-foreground">
          {connected ? "● live" : "○ disconnected"}
        </span>
```

with:

```tsx
        <span className="text-xs text-muted-foreground">
          {replay ? "↺ replay" : connected ? "● live" : "○ disconnected"}
        </span>
```

Then add the toggle as the first item in the `ml-auto` action cluster (immediately after `<div className="ml-auto flex items-center gap-2">`):

```tsx
          <Button
            size="sm"
            variant={replay ? "default" : "outline"}
            onClick={() => setReplay((r) => !r)}
          >
            {replay ? "Exit replay" : "Replay"}
          </Button>
```

- [ ] **Step 5: Render ReplayBar in replay mode**

Immediately after the closing `</div>` of the toolbar row (the `flex items-center gap-3 border-b ...` div), add:

```tsx
      {replay && <ReplayBar sessionId={sessionId} />}
```

- [ ] **Step 6: Typecheck + lint**

Run: `npm run typecheck && npm run lint`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/s/[sessionId]/SessionGraphView.tsx
git commit -m "feat(replay): toggle replay mode on the session page"
```

---

## Manual smoke (user — after all tasks)

Dev server doesn't survive the agent env (per `kodoku-known-followups`); the owner verifies:

1. Free port 3000, start the frontend, start the backend.
2. Open a session that has events (any run, or click "Emit debug events").
3. Click **Replay**: graph resets to final state, indicator shows `↺ replay`, live socket closed.
4. Drag the slider to 0 → graph empties; step forward → nodes appear/score/prune in order.
5. **Play** → auto-advances and stops at the end; **Pause** mid-way works.
6. Click **Exit replay** → reconnects live (`● live`), graph reseeds.

## Self-review notes

- Spec coverage: setGraph (T1) ✓, graphAtCursor (T1) ✓, ReplayBar fetch/cursor/clock/empty-state (T2) ✓, toggle + effect guard + reuse of Graph/NodeDrawer (T3) ✓, fixed rate / no speed control ✓, no backend ✓.
- No new dependency: native range input + existing `Button` + `lucide-react` (already a dependency).
- Backward step correctness: every cursor change refolds from `emptyGraph()` via `graphAtCursor` (T1), not `applyEvent`.
