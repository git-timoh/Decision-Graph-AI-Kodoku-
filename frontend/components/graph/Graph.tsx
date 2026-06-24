"use client";

import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";

import { NodeCard } from "@/components/graph/NodeCard";
import { layoutTree } from "@/components/graph/layout";
import { useSessionStore } from "@/state/sessionStore";
import type { GraphNode } from "@/lib/ws/types";

const nodeTypes = { card: NodeCard };

export function Graph() {
  const graphNodes = useSessionStore((s) => s.graph.nodes);
  const selectNode = useSessionStore((s) => s.selectNode);

  const { nodes, edges } = useMemo(() => {
    const list = Object.values(graphNodes);
    const rfNodes: Node<GraphNode>[] = list.map((n) => ({
      id: n.id,
      type: "card",
      data: n,
      position: { x: 0, y: 0 },
    }));
    const rfEdges: Edge[] = list
      .filter((n) => n.parent_id && graphNodes[n.parent_id])
      .map((n) => ({
        id: `${n.parent_id}->${n.id}`,
        source: n.parent_id as string,
        target: n.id,
        animated: n.status === "active",
      }));
    return { nodes: layoutTree(rfNodes, rfEdges), edges: rfEdges };
  }, [graphNodes]);

  if (nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No nodes yet — run the engine to populate the graph.
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      proOptions={{ hideAttribution: true }}
      onNodeClick={(_, node) => selectNode(node.id)}
    >
      <Background />
      <Controls />
    </ReactFlow>
  );
}
