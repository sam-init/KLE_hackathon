"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Edge,
  MiniMap,
  Node,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { GraphPayload } from "@/lib/types";
import { toGraphData } from "@/utils/graphAdapter";

type GraphViewProps = {
  graph?: GraphPayload | null;
  selectedPath?: string | null;
  onNodeSelect?: (filePath: string | null) => void;
};

function GraphViewContent({ graph, selectedPath, onNodeSelect }: GraphViewProps) {
  const mapped = useMemo(() => toGraphData(graph), [graph]);
  const linkedMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    mapped.links.forEach((link) => {
      if (!map.has(link.source)) map.set(link.source, new Set());
      if (!map.has(link.target)) map.set(link.target, new Set());
      map.get(link.source)?.add(link.target);
      map.get(link.target)?.add(link.source);
    });
    return map;
  }, [mapped.links]);

  const initialNodes: Node[] = useMemo(
    () =>
      mapped.nodes.map((node, index) => {
        const colCount = Math.max(3, Math.ceil(Math.sqrt(mapped.nodes.length)));
        const x = 120 + (index % colCount) * 220;
        const y = 80 + Math.floor(index / colCount) * 130;
        return {
          id: node.id,
          data: { label: node.label, filePath: node.filePath, kind: node.kind },
          position: { x, y },
          style: {
            background: "#161b22",
            color: "#e6edf3",
            border: "1px solid #30363d",
            borderRadius: 10,
            width: 180,
            padding: "10px 12px",
            fontSize: 12,
          },
        };
      }),
    [mapped.nodes]
  );

  const initialEdges: Edge[] = useMemo(
    () =>
      mapped.links.map((link, index) => ({
        id: `e-${link.source}-${link.target}-${index}`,
        source: link.source,
        target: link.target,
        animated: false,
        style: { stroke: "#3f4952", strokeWidth: 1.4 },
        label: link.label || undefined,
        labelStyle: { fill: "#8b949e", fontSize: 10 },
      })),
    [mapped.links]
  );

  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
    setActiveNodeId(null);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  useEffect(() => {
    if (!selectedPath) return;
    const selectedNode = mapped.nodes.find((node) => node.filePath === selectedPath);
    if (!selectedNode) return;
    setActiveNodeId(selectedNode.id);
  }, [mapped.nodes, selectedPath]);

  useEffect(() => {
    if (!activeNodeId) {
      setNodes((current) =>
        current.map((node) => ({
          ...node,
          style: {
            ...node.style,
            opacity: 1,
            borderColor: "#30363d",
            boxShadow: "none",
          },
        }))
      );
      setEdges((current) =>
        current.map((edge) => ({
          ...edge,
          animated: false,
          style: { ...edge.style, opacity: 0.75, stroke: "#3f4952", strokeWidth: 1.4 },
        }))
      );
      return;
    }

    const connected = linkedMap.get(activeNodeId) ?? new Set<string>();
    setNodes((current) =>
      current.map((node) => {
        const isActive = node.id === activeNodeId;
        const isConnected = connected.has(node.id);
        return {
          ...node,
          style: {
            ...node.style,
            opacity: isActive || isConnected ? 1 : 0.25,
            borderColor: isActive ? "#58a6ff" : isConnected ? "#3fb950" : "#30363d",
            boxShadow: isActive ? "0 0 0 1px #58a6ff, 0 0 18px rgba(88,166,255,0.3)" : "none",
          },
        };
      })
    );
    setEdges((current) =>
      current.map((edge) => {
        const isConnected = edge.source === activeNodeId || edge.target === activeNodeId;
        return {
          ...edge,
          animated: isConnected,
          style: {
            ...edge.style,
            opacity: isConnected ? 1 : 0.2,
            stroke: isConnected ? "#58a6ff" : "#3f4952",
            strokeWidth: isConnected ? 1.8 : 1.2,
          },
        };
      })
    );
  }, [activeNodeId, linkedMap, setEdges, setNodes]);

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      const nextId = activeNodeId === node.id ? null : node.id;
      setActiveNodeId(nextId);
      if (!onNodeSelect) return;
      if (!nextId) {
        onNodeSelect(null);
        return;
      }
      const filePath = String(node.data?.filePath || "");
      onNodeSelect(filePath || null);
    },
    [activeNodeId, onNodeSelect]
  );

  if (mapped.nodes.length === 0) {
    return (
      <div className="card empty-state">
        <div className="icon">🕸️</div>
        <h3>Graph View</h3>
        <p>No dependency graph data available yet.</p>
      </div>
    );
  }

  return (
    <div className="card graph-view-card">
      <div className="graph-view-header">
        <h3>Graph View</h3>
        <span>{mapped.nodes.length} nodes · {mapped.links.length} links</span>
      </div>
      <div className="graph-canvas">
        <ReactFlow
          fitView
          colorMode="dark"
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          minZoom={0.2}
          maxZoom={1.8}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#2c3138" gap={20} />
          <MiniMap
            pannable
            zoomable
            style={{ background: "#0d1117", border: "1px solid #30363d" }}
            nodeColor="#58a6ff"
          />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}

export function GraphView(props: GraphViewProps) {
  return (
    <ReactFlowProvider>
      <GraphViewContent {...props} />
    </ReactFlowProvider>
  );
}
