"use client";

import { useEffect, useState } from "react";

import { Graph } from "@/components/graph/Graph";
import { Button } from "@/components/ui/button";
import { connectSession } from "@/lib/ws/client";
import type { GraphNode } from "@/lib/ws/types";
import type { EvaluationDTO, NodeDTO } from "@/lib/types/api";
import { useSessionStore } from "@/state/sessionStore";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const STATUS_STYLE: Record<string, string> = {
  idle: "bg-muted text-muted-foreground",
  running: "bg-blue-500/15 text-blue-600",
  awaiting_human: "bg-amber-500/15 text-amber-600",
  done: "bg-emerald-500/15 text-emerald-600",
  error: "bg-red-500/15 text-red-600",
};

function seedNodes(nodes: NodeDTO[], evaluations: EvaluationDTO[]): GraphNode[] {
  const scoreByNode = new Map(evaluations.map((e) => [e.node_id, e]));
  return nodes.map((n) => {
    const ev = scoreByNode.get(n.id);
    return {
      id: n.id,
      parent_id: n.parent_id ?? null,
      depth: n.depth,
      kind: n.kind as GraphNode["kind"],
      title: n.title,
      content: n.content,
      status: n.status as GraphNode["status"],
      score: ev ? Number(ev.score) : undefined,
      critique: ev?.critique,
    };
  });
}

type Props = {
  sessionId: string;
  initialNodes: NodeDTO[];
  initialEvaluations: EvaluationDTO[];
};

export function SessionGraphView({
  sessionId,
  initialNodes,
  initialEvaluations,
}: Props) {
  const seedGraph = useSessionStore((s) => s.seedGraph);
  const applyEvent = useSessionStore((s) => s.applyEvent);
  const setConnected = useSessionStore((s) => s.setConnected);
  const status = useSessionStore((s) => s.graph.status);
  const synthesis = useSessionStore((s) => s.graph.synthesis);
  const connected = useSessionStore((s) => s.connected);
  const [emitting, setEmitting] = useState(false);

  useEffect(() => {
    seedGraph(seedNodes(initialNodes, initialEvaluations));
    const disconnect = connectSession(sessionId, {
      apply: applyEvent,
      getSince: () => useSessionStore.getState().graph.lastSeenEventId,
      onConnected: setConnected,
    });
    return disconnect;
  }, [sessionId, initialNodes, initialEvaluations, seedGraph, applyEvent, setConnected]);

  async function emitDebug() {
    setEmitting(true);
    try {
      await fetch(`${API_BASE}/sessions/${sessionId}/debug/emit`, {
        method: "POST",
      });
    } finally {
      setEmitting(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-6 py-3">
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            STATUS_STYLE[status] ?? STATUS_STYLE.idle
          }`}
        >
          {status}
        </span>
        <span className="text-xs text-muted-foreground">
          {connected ? "● live" : "○ disconnected"}
        </span>
        <div className="ml-auto">
          <Button size="sm" variant="outline" onClick={emitDebug} disabled={emitting}>
            {emitting ? "Emitting…" : "Emit debug events"}
          </Button>
        </div>
      </div>

      <div className="relative flex-1">
        <Graph />
      </div>

      {synthesis && (
        <div className="border-t border-border bg-card px-6 py-4">
          <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Synthesis
          </h2>
          <p className="mt-1 whitespace-pre-wrap text-sm">{synthesis}</p>
        </div>
      )}
    </div>
  );
}
