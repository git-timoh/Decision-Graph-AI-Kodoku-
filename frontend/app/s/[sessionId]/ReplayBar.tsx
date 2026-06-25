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
