import { Handle, Position } from "reactflow";

import { cn } from "@/lib/utils";
import type { GraphNode } from "@/lib/ws/types";

const STATUS_RING: Record<GraphNode["status"], string> = {
  pending: "border-border",
  active: "border-blue-400",
  kept: "border-emerald-400",
  expanded: "border-violet-400",
  pruned: "border-border opacity-40 line-through",
};

const KIND_LABEL: Record<GraphNode["kind"], string> = {
  root: "Goal",
  candidate: "Idea",
  synthesis: "Synthesis",
};

export function NodeCard({ data }: { data: GraphNode }) {
  return (
    <div
      className={cn(
        "w-[240px] rounded-lg border-2 bg-card p-3 shadow-sm transition-all",
        STATUS_RING[data.status],
      )}
    >
      {data.kind !== "root" && <Handle type="target" position={Position.Top} />}
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {KIND_LABEL[data.kind]}
        </span>
        {data.score !== undefined && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold tabular-nums">
            {data.score.toFixed(1)}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm font-medium leading-snug">{data.title}</p>
      <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
        {data.content}
      </p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
