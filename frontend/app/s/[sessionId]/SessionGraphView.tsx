"use client";

import { useEffect, useState } from "react";

import { Graph } from "@/components/graph/Graph";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { connectSession } from "@/lib/ws/client";
import type { EngineStatus, GraphNode } from "@/lib/ws/types";
import type { EvaluationDTO, NodeDTO } from "@/lib/types/api";
import { useSessionStore } from "@/state/sessionStore";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  idle: "bg-muted text-muted-foreground",
  running: "bg-blue-500/15 text-blue-600",
  awaiting_human: "bg-amber-500/15 text-amber-600",
  done: "bg-emerald-500/15 text-emerald-600",
  error: "bg-red-500/15 text-red-600",
  paused: "bg-amber-500/15 text-amber-600",
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
  initialStatus: EngineStatus;
  initialSynthesis: string | null;
  initialNodes: NodeDTO[];
  initialEvaluations: EvaluationDTO[];
};

export function SessionGraphView({
  sessionId,
  initialStatus,
  initialSynthesis,
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
  const [running, setRunning] = useState(false);
  const [interrupting, setInterrupting] = useState(false);
  const canRun = status === "draft" || status === "paused" || status === "error";

  useEffect(() => {
    seedGraph(seedNodes(initialNodes, initialEvaluations), {
      status: initialStatus,
      synthesis: initialSynthesis ?? "",
    });
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
  ]);

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

  async function runSession() {
    setRunning(true);
    try {
      await api.runSession(sessionId);
    } finally {
      setRunning(false);
    }
  }

  async function interruptSession() {
    setInterrupting(true);
    try {
      await api.interruptSession(sessionId);
    } finally {
      setInterrupting(false);
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
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={emitDebug} disabled={emitting}>
            {emitting ? "Emitting…" : "Emit debug events"}
          </Button>
          {status === "running" && (
            <Button
              size="sm"
              variant="outline"
              onClick={interruptSession}
              disabled={interrupting}
            >
              {interrupting ? "Interrupting…" : "Interrupt"}
            </Button>
          )}
          <Button
            size="sm"
            onClick={runSession}
            disabled={!canRun || running}
          >
            {running ? "Starting…" : "Run"}
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
