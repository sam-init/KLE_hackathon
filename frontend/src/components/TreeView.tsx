"use client";

import {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import { useMemo } from "react";

import {
  TreeNode,
  VisualizationBundle,
  getConnectedNodeIds,
  getGroupColor,
  getNodeGroupFromPath,
} from "@/src/utils/graphAdapter";

type Props = {
  tree: TreeNode;
  graph: VisualizationBundle["graph"];
  selectedNodeId?: string | null;
  onNodeSelect?: (nodeId: string | null) => void;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
};

type LayoutNode = {
  id: string;
  x: number;
  y: number;
  depth: number;
  group: string;
  type: "folder" | "file";
  name: string;
  path: string;
  fileCount: number;
};

function toRgb(color: string): string {
  const normalized = color.replace("#", "");
  const expanded =
    normalized.length === 3
      ? normalized
          .split("")
          .map((char) => char + char)
          .join("")
      : normalized;
  const value = Number.parseInt(expanded, 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  return `${red}, ${green}, ${blue}`;
}

function buildTreeLayout(tree: TreeNode) {
  const layoutNodes: LayoutNode[] = [];
  const edges: Edge[] = [];
  let leafIndex = 0;

  function visit(node: TreeNode, parent: TreeNode | null): number {
    const childYs = node.children.map((child) => visit(child, node));
    const y = childYs.length > 0 ? childYs.reduce((a, b) => a + b, 0) / childYs.length : leafIndex++ * 108 + 72;
    const group = node.type === "file" ? getNodeGroupFromPath(node.path) : "root";

    layoutNodes.push({
      id: node.id,
      x: node.depth * 280 + 80,
      y,
      depth: node.depth,
      group,
      type: node.type,
      name: node.name,
      path: node.path,
      fileCount: node.fileCount,
    });

    if (parent) {
      const edgeColor =
        node.type === "file" ? getGroupColor(group) : "rgba(71, 85, 105, 0.42)";
      edges.push({
        id: `${parent.id}->${node.id}`,
        source: parent.id,
        target: node.id,
        type: "smoothstep",
        animated: false,
        markerEnd:
          node.type === "file"
            ? {
                type: MarkerType.ArrowClosed,
                width: 16,
                height: 16,
                color: edgeColor,
              }
            : undefined,
        style: {
          stroke: edgeColor,
          strokeWidth: node.type === "file" ? 2.4 : 1.4,
          opacity: 0.92,
        },
      });
    }

    return y;
  }

  visit(tree, null);
  return { layoutNodes, edges };
}

function makeFlowNodes(
  layoutNodes: LayoutNode[],
  selectedNodeId: string | null,
  connectedNodeIds: Set<string>,
): Node[] {
  const hasSelection = Boolean(selectedNodeId);

  return layoutNodes.map((node) => {
    const groupTint = getGroupColor(node.group);
    const isSelected = node.id === selectedNodeId;
    const isConnected = connectedNodeIds.has(node.id);
    const isFile = node.type === "file";

    return {
      id: node.id,
      position: { x: node.x, y: node.y },
      draggable: false,
      selectable: true,
      data: {
        tint: groupTint,
        label: (
          <div className={`treeviz-node ${isFile ? "file" : "folder"}`}>
            <span
              className={`treeviz-dot ${isFile ? "file" : "folder"}`}
              style={{
                backgroundColor: isFile ? groupTint : "rgba(51, 65, 85, 0.92)",
                boxShadow: isFile
                  ? `0 0 18px rgba(${toRgb(groupTint)}, 0.42)`
                  : "none",
              }}
            />
            <div className="treeviz-copy">
              <strong>{node.name}</strong>
              <span>{isFile ? node.path : `${node.fileCount} files`}</span>
            </div>
          </div>
        ),
      },
      style: {
        border: "none",
        borderRadius: 12,
        background: "transparent",
        color: isFile ? "#e2e8f0" : "#94a3b8",
        boxShadow: "none",
        opacity: hasSelection && !isSelected && !isConnected ? 0.24 : 1,
      },
    };
  });
}

function makeFlowEdges(
  baseEdges: Edge[],
  selectedNodeId: string | null,
  connectedNodeIds: Set<string>,
): Edge[] {
  const hasSelection = Boolean(selectedNodeId);

  return baseEdges.map((edge) => {
    const isConnected =
      connectedNodeIds.has(edge.source) && connectedNodeIds.has(edge.target);

    return {
      ...edge,
      animated: Boolean(selectedNodeId && isConnected),
      style: {
        ...edge.style,
        opacity: hasSelection && !isConnected ? 0.12 : 0.96,
        stroke: isConnected ? "#7dd3fc" : edge.style?.stroke,
      },
    };
  });
}

function TreeCanvas({
  tree,
  graph,
  selectedNodeId,
  onNodeSelect,
  isExpanded = false,
  onToggleExpand,
}: Props) {
  const { layoutNodes, edges } = useMemo(() => buildTreeLayout(tree), [tree]);
  const connectedNodeIds = useMemo(
    () => getConnectedNodeIds(graph, selectedNodeId ?? null),
    [graph, selectedNodeId],
  );
  const nodes = useMemo(
    () => makeFlowNodes(layoutNodes, selectedNodeId ?? null, connectedNodeIds),
    [connectedNodeIds, layoutNodes, selectedNodeId],
  );
  const flowEdges = useMemo(
    () => makeFlowEdges(edges, selectedNodeId ?? null, connectedNodeIds),
    [connectedNodeIds, edges, selectedNodeId],
  );

  return (
    <div className="viz-panel tree-panel treeviz-panel">
      <div className="viz-panel-header">
        <div>
          <h3>Tree View</h3>
          <p>Repository structure in a visual tree with group-aware file colors.</p>
        </div>
        <div className="viz-badge-row">
          <button
            type="button"
            className="btn btn-secondary btn-sm viz-expand-btn"
            onClick={onToggleExpand}
          >
            {isExpanded ? "Exit Expanded View" : "Expand Tree"}
          </button>
          <span className="viz-badge">{layoutNodes.length} items</span>
        </div>
      </div>

      <div className="treeviz-canvas">
        <ReactFlow
          nodes={nodes}
          edges={flowEdges}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          zoomOnDoubleClick={false}
          minZoom={0.4}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
          colorMode="dark"
          onNodeClick={(_, node) => onNodeSelect?.(node.id)}
          onPaneClick={() => onNodeSelect?.(null)}
        >
          <Background gap={24} size={1} color="rgba(51, 65, 85, 0.36)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}

export function TreeView(props: Props) {
  return (
    <ReactFlowProvider>
      <TreeCanvas {...props} />
    </ReactFlowProvider>
  );
}
