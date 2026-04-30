"use client";

import { useEffect, useMemo, useState } from "react";

import { TreeNode } from "@/src/utils/graphAdapter";

type Props = {
  tree: TreeNode;
  selectedNodeId?: string | null;
  onNodeSelect?: (nodeId: string) => void;
};

function collectExpandedDefaults(tree: TreeNode): string[] {
  const expanded: string[] = [tree.id];

  for (const child of tree.children) {
    if (child.type === "folder") expanded.push(child.id);
  }

  return expanded;
}

export function TreeView({ tree, selectedNodeId, onNodeSelect }: Props) {
  const initialExpanded = useMemo(() => collectExpandedDefaults(tree), [tree]);
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(initialExpanded),
  );

  useEffect(() => {
    setExpanded(new Set(initialExpanded));
  }, [initialExpanded]);

  function toggle(nodeId: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }

  function renderNode(node: TreeNode) {
    const isFolder = node.type === "folder";
    const isOpen = expanded.has(node.id);
    const isSelected = selectedNodeId === node.id;

    return (
      <div key={node.id} className="tree-node-wrap">
        <div
          className={`tree-node ${isSelected ? "selected" : ""}`}
          style={{ paddingLeft: `${12 + node.depth * 14}px` }}
        >
          <button
            type="button"
            className={`tree-node-button ${isFolder ? "folder" : "file"}`}
            onClick={() => {
              if (isFolder) toggle(node.id);
              else onNodeSelect?.(node.id);
            }}
          >
            <span className={`tree-caret ${isOpen ? "open" : ""}`}>
              {isFolder ? ">" : " "}
            </span>
            <span className="tree-icon">{isFolder ? "[]" : "{}"}</span>
            <span className="tree-label">{node.name}</span>
          </button>
          <button
            type="button"
            className="tree-meta"
            onClick={() => onNodeSelect?.(node.id)}
          >
            {isFolder ? `${node.fileCount} files` : "inspect"}
          </button>
        </div>

        {isFolder && isOpen && node.children.length > 0 && (
          <div>{node.children.map(renderNode)}</div>
        )}
      </div>
    );
  }

  return (
    <div className="viz-panel tree-panel">
      <div className="viz-panel-header">
        <div>
          <h3>Tree View</h3>
          <p>Browse folders and files, then sync selection with the graph.</p>
        </div>
      </div>
      <div className="tree-scroll">{renderNode(tree)}</div>
    </div>
  );
}
