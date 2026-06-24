"use client";

import { useMemo } from "react";
import { ChevronRight, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { GraphNode } from "@/lib/ws/types";
import { useSessionStore } from "@/state/sessionStore";

const STATUS_BADGE: Record<GraphNode["status"], string> = {
  pending: "bg-muted text-muted-foreground",
  active: "bg-blue-500/15 text-blue-600",
  kept: "bg-emerald-500/15 text-emerald-600",
  expanded: "bg-violet-500/15 text-violet-600",
  pruned: "bg-muted text-muted-foreground line-through",
};

const KIND_LABEL: Record<GraphNode["kind"], string> = {
  root: "Goal",
  candidate: "Idea",
  synthesis: "Synthesis",
};

/** Walks `parent_id` up from `node` to the root, returning [root, ..., node]. */
function buildPath(node: GraphNode, nodes: Record<string, GraphNode>): GraphNode[] {
  const path: GraphNode[] = [node];
  const seen = new Set<string>([node.id]);
  let current = node;
  while (current.parent_id) {
    const parent = nodes[current.parent_id];
    if (!parent || seen.has(parent.id)) break;
    path.unshift(parent);
    seen.add(parent.id);
    current = parent;
  }
  return path;
}

export function NodeDrawer() {
  const nodes = useSessionStore((s) => s.graph.nodes);
  const selectedNodeId = useSessionStore((s) => s.selectedNodeId);
  const clearSelection = useSessionStore((s) => s.clearSelection);

  const node = selectedNodeId ? nodes[selectedNodeId] : null;
  const path = useMemo(() => (node ? buildPath(node, nodes) : []), [node, nodes]);

  if (!node) return null;

  const dimEntries = Object.entries(node.dimensions ?? {});

  return (
    <div className="absolute inset-0 z-20 flex justify-start">
      <div
        className="absolute inset-0 bg-black/40 animate-in fade-in-0"
        aria-hidden="true"
        onClick={clearSelection}
      />
      <div
        className={cn(
          "relative flex h-full w-full max-w-md flex-col border-r border-border bg-card shadow-2xl",
          "animate-in slide-in-from-left duration-200",
        )}
        role="dialog"
        aria-label="Node detail"
      >
        <div className="flex items-start justify-between border-b border-border px-5 py-4">
          <div className="min-w-0">
            {path.length > 1 && (
              <nav className="mb-2 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                {path.map((ancestor, i) => (
                  <span key={ancestor.id} className="flex items-center gap-1">
                    {i > 0 && <ChevronRight className="h-3 w-3" />}
                    <span
                      className={cn(
                        i === path.length - 1 && "font-medium text-foreground",
                      )}
                    >
                      {ancestor.title}
                    </span>
                  </span>
                ))}
              </nav>
            )}
            <span className="rounded bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {KIND_LABEL[node.kind]}
            </span>
            <h2 className="mt-2 text-sm font-semibold leading-snug">{node.title}</h2>
          </div>
          <button
            type="button"
            onClick={clearSelection}
            className="shrink-0 rounded p-1 text-muted-foreground transition-opacity hover:bg-accent hover:text-foreground"
            aria-label="Close node detail"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-auto px-5 py-4">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "rounded px-2 py-0.5 text-xs font-medium",
                STATUS_BADGE[node.status],
              )}
            >
              {node.status}
            </span>
            {node.score !== undefined && (
              <span className="rounded bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums">
                Score {node.score.toFixed(1)}
              </span>
            )}
            {node.model && (
              <span className="rounded bg-muted px-2 py-0.5 text-xs font-medium">
                {node.model}
              </span>
            )}
          </div>

          <h3 className="mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Content
          </h3>
          <p className="mt-1 whitespace-pre-wrap text-sm">{node.content}</p>

          {node.critique && (
            <>
              <h3 className="mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Critique
              </h3>
              <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
                {node.critique}
              </p>
            </>
          )}

          {dimEntries.length > 0 && (
            <>
              <h3 className="mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Dimensions
              </h3>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {dimEntries.map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between rounded border border-border px-2.5 py-1.5 text-xs"
                  >
                    <span className="text-muted-foreground">{key}</span>
                    <span className="font-semibold tabular-nums">{value.toFixed(1)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
