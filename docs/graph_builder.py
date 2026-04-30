from __future__ import annotations

from typing import Any


def build_dependency_graph(parsed_files: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = []
    edges = []
    seen = set()

    for item in parsed_files:
        file_id = item["path"]
        if file_id not in seen:
            nodes.append({"id": file_id, "label": file_id.split("/")[-1], "kind": "file"})
            seen.add(file_id)

        for imp in item.get("imports", []):
            imp_id = f"dep::{imp}"
            if imp_id not in seen:
                nodes.append({"id": imp_id, "label": imp, "kind": "dependency"})
                seen.add(imp_id)
            edges.append({"source": file_id, "target": imp_id, "label": "imports"})

    return {"nodes": nodes, "edges": edges}


def build_execution_flowchart(parsed_files: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = []
    edges = []

    for item in parsed_files:
        file_id = item["path"]
        nodes.append({"id": file_id, "label": file_id.split("/")[-1], "kind": "module"})

        functions = item.get("functions", [])
        for fn in functions:
            fn_id = f"{file_id}::{fn['name']}"
            nodes.append({"id": fn_id, "label": fn["name"], "kind": "function"})
            edges.append({"source": file_id, "target": fn_id, "label": "defines"})

    return {"nodes": _dedupe_nodes(nodes), "edges": edges}


def build_knowledge_graph(parsed_files: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = []
    edges = []

    for item in parsed_files:
        file_id = item["path"]
        nodes.append({"id": file_id, "label": file_id.split("/")[-1], "kind": "file"})

        for cls in item.get("classes", []):
            cls_id = f"{file_id}::class::{cls['name']}"
            nodes.append({"id": cls_id, "label": cls["name"], "kind": "class"})
            edges.append({"source": file_id, "target": cls_id, "label": "contains"})

            for method_name in cls.get("methods", []):
                method_id = f"{cls_id}::method::{method_name}"
                nodes.append({"id": method_id, "label": method_name, "kind": "method"})
                edges.append({"source": cls_id, "target": method_id, "label": "has_method"})

        for fn in item.get("functions", []):
            fn_id = f"{file_id}::fn::{fn['name']}"
            nodes.append({"id": fn_id, "label": fn["name"], "kind": "function"})
            edges.append({"source": file_id, "target": fn_id, "label": "contains"})

    return {"nodes": _dedupe_nodes(nodes), "edges": edges}


def _dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for n in nodes:
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        out.append(n)
    return out
