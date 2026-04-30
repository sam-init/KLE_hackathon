from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from typing import Any


def _normalize_repo_path(path: str) -> str:
    clean = path.replace("\\", "/").strip()
    if not clean:
        return ""
    for marker in ("/src/", "/workspace/", "/tmp/", "/var/", "/opt/", "/home/"):
        if marker in clean:
            clean = clean.split(marker, 1)[-1]
    return clean.lstrip("/")


def _looks_like_system_path(path: str) -> bool:
    lowered = path.lower()
    return lowered.startswith(("/", "c:/", "d:/", "e:/")) or "/opt/render/" in lowered or "/tmp/" in lowered


def _sanitize_files(parsed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in parsed_files:
        clean_path = _normalize_repo_path(str(item.get("path", "")))
        if not clean_path or _looks_like_system_path(clean_path):
            continue
        clean = dict(item)
        clean["path"] = clean_path
        out.append(clean)
    return out


def _build_tree(paths: list[str], max_lines: int = 40) -> str:
    if not paths:
        return ""
    tree: dict[str, Any] = {}
    for path in sorted(set(paths)):
        cursor = tree
        for part in [p for p in PurePosixPath(path).parts if p]:
            cursor = cursor.setdefault(part, {})
    lines: list[str] = []

    def walk(node: dict[str, Any], prefix: str = "") -> None:
        keys = sorted(node.keys())
        for idx, name in enumerate(keys):
            last = idx == len(keys) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}")
            walk(node[name], prefix + ("    " if last else "│   "))

    walk(tree)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["..."]
    return "```text\n" + "\n".join(lines) + "\n```"


def _top_language_counts(parsed_files: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item.get("language", "unknown")).lower() for item in parsed_files)
    return {k: v for k, v in counts.items() if k and k != "unknown"}


def _detect_project_types(parsed_files: list[dict[str, Any]]) -> list[str]:
    paths = [item["path"].lower() for item in parsed_files]
    imports = " ".join(imp.lower() for item in parsed_files for imp in item.get("imports", []))
    types: list[str] = []
    if any(p.endswith((".v", ".sv", ".vh", ".svh")) for p in paths):
        types.append("Hardware/HDL")
    if "fastapi" in imports or "flask" in imports or any("/api/" in p or "server" in p for p in paths):
        types.append("Backend API")
    if any(p.endswith((".tsx", ".jsx")) or p.startswith("frontend/") for p in paths):
        types.append("Frontend Web")
    if "rag" in " ".join(paths):
        types.append("Retrieval Pipeline")
    if any("github" in p or "webhook" in p for p in paths):
        types.append("GitHub Integration")
    if any("test" in p for p in paths):
        types.append("Test Suite")
    return types or ["General Codebase"]


def _build_module_graph(parsed_files: list[dict[str, Any]]) -> dict[str, set[str]]:
    path_set = {item["path"] for item in parsed_files}
    by_stem: dict[str, str] = {}
    for path in path_set:
        stem = PurePosixPath(path).stem
        if stem and stem not in by_stem:
            by_stem[stem] = path
    edges: dict[str, set[str]] = {path: set() for path in path_set}
    for item in parsed_files:
        src = item["path"]
        for imp in item.get("imports", []):
            name = str(imp).split(".")[0]
            target = by_stem.get(name)
            if target and target != src:
                edges[src].add(target)
    return edges


def _entrypoints(parsed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in parsed_files:
        p = item["path"].lower()
        score = 0
        if p.endswith(("main.py", "app.py", "server.py", "manage.py", "index.ts", "index.js")):
            score += 5
        if "main" in p or "server" in p or "cli" in p:
            score += 2
        if len(item.get("imports", [])) > 4:
            score += 1
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked[:3]]


def _infer_purpose(parsed_files: list[dict[str, Any]]) -> str:
    tokens: Counter[str] = Counter()
    for item in parsed_files:
        path = item["path"].lower()
        for part in PurePosixPath(path).parts:
            if len(part) > 2:
                tokens[part.replace(".", "_")] += 1
        for fn in item.get("functions", [])[:12]:
            name = str(fn.get("name", "")).lower()
            if name:
                tokens[name] += 1
        for imp in item.get("imports", [])[:12]:
            tokens[str(imp).lower().split(".")[0]] += 1
    hints = []
    for key, phrase in (
        ("review", "code review"),
        ("doc", "documentation generation"),
        ("readme", "README generation"),
        ("parser", "source parsing"),
        ("graph", "dependency visualization"),
        ("github", "GitHub automation"),
        ("webhook", "webhook-triggered workflows"),
        ("api", "API endpoints"),
        ("rag", "retrieval-augmented analysis"),
        ("verilog", "HDL analysis"),
    ):
        if any(tok.startswith(key) for tok in tokens):
            hints.append(phrase)
    if not hints:
        return "The repository focuses on processing source files and producing derived developer outputs."
    joined = ", ".join(dict.fromkeys(hints))
    return f"The system is built around {joined}, inferred from module names, symbols, and imports."


def _group_paths(paths: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for path in sorted(paths):
        folder = path.split("/", 1)[0] if "/" in path else "root"
        groups.setdefault(folder, []).append(path)
    return groups


def _module_role(item: dict[str, Any]) -> str:
    p = item["path"].lower()
    fn_count = len(item.get("functions", []))
    cls_count = len(item.get("classes", []))
    imports = " ".join(str(x).lower() for x in item.get("imports", []))
    if any(k in p for k in ("main", "app", "server", "cli")):
        return "Entry or orchestration module."
    if any(k in p for k in ("route", "controller", "api")):
        return "Request/response boundary module."
    if any(k in p for k in ("service", "agent", "orchestrator", "pipeline")):
        return "Processing/service logic."
    if any(k in p for k in ("parser", "loader", "ingest")):
        return "Ingestion/parsing module."
    if "react" in imports or p.endswith((".tsx", ".jsx")):
        return "UI component module."
    if cls_count > fn_count:
        return "Class-oriented domain logic."
    if fn_count:
        return "Function-oriented helper/business logic."
    return "Support module."


def analyze_project(parsed_files: list[dict[str, Any]]) -> dict[str, Any]:
    files = _sanitize_files(parsed_files)
    languages = _top_language_counts(files)
    paths = [item["path"] for item in files]
    groups = _group_paths(paths)
    graph = _build_module_graph(files)
    entry = _entrypoints(files)
    flow_steps: list[str] = []
    if entry:
        flow_steps.append(f"entrypoint: `{entry[0]['path']}`")
    if any("ingest" in p or "loader" in p or "parser" in p for p in paths):
        flow_steps.append("ingest/parse source files")
    if any("service" in p or "agent" in p or "review" in p or "doc" in p for p in paths):
        flow_steps.append("process through service/reasoning modules")
    if any("rag" in p or "store" in p or "cache" in p for p in paths):
        flow_steps.append("store/retrieve indexed context")
    if any("github" in p or "webhook" in p for p in paths):
        flow_steps.append("publish results to GitHub integration points")
    if not flow_steps:
        flow_steps.append("execute module logic based on detected entrypoints and imports")
    return {
        "files": files,
        "languages": languages,
        "project_types": _detect_project_types(files),
        "purpose": _infer_purpose(files),
        "groups": groups,
        "graph": graph,
        "entrypoints": entry,
        "flow_steps": flow_steps,
    }


def _render_overview(understanding: dict[str, Any]) -> str:
    file_count = len(understanding["files"])
    lang_line = ", ".join(f"{k}: {v}" for k, v in understanding["languages"].items()) or "unknown"
    project_types = ", ".join(understanding["project_types"])
    return (
        f"{understanding['purpose']}\n\n"
        f"- Detected project type: {project_types}\n"
        f"- Parsed source surface: {file_count} files\n"
        f"- Language profile: {lang_line}"
    )


def _render_architecture(understanding: dict[str, Any]) -> str:
    steps = understanding["flow_steps"]
    if not steps:
        return ""
    return "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(steps))


def _render_structure(understanding: dict[str, Any]) -> str:
    grouped_lines: list[str] = []
    for group, paths in understanding["groups"].items():
        grouped_lines.append(f"- **{group}/** ({len(paths)} files)")
    tree = _build_tree([item["path"] for item in understanding["files"]])
    if not tree:
        return ""
    return "\n".join(grouped_lines[:12]) + "\n\n" + tree


def _render_modules(understanding: dict[str, Any], max_items: int = 14) -> str:
    ranked = sorted(
        understanding["files"],
        key=lambda x: (len(x.get("imports", [])) + len(x.get("functions", [])) + len(x.get("classes", [])), x.get("line_count", 0)),
        reverse=True,
    )[:max_items]
    lines: list[str] = []
    for item in ranked:
        fns = [str(f.get("name")) for f in item.get("functions", [])[:3] if f.get("name")]
        cls = [str(c.get("name")) for c in item.get("classes", [])[:2] if c.get("name")]
        sym = ", ".join([*(f"`{x}`" for x in cls), *(f"`{x}()`" for x in fns)])
        extras = f" Key symbols: {sym}." if sym else ""
        lines.append(f"- **`{item['path']}`**: {_module_role(item)}{extras}")
    return "\n".join(lines)


def _usage_for_entry(entry: dict[str, Any]) -> str:
    path = entry["path"]
    lower = path.lower()
    if lower.endswith(".py"):
        return f"```bash\npython {path}\n```"
    if lower.endswith(".js"):
        return f"```bash\nnode {path}\n```"
    if lower.endswith(".ts"):
        return f"```bash\nnpx ts-node {path}\n```"
    if lower.endswith((".v", ".sv")):
        return f"```text\nUse your HDL simulator/synthesis tool with entry file: {path}\n```"
    return ""


def create_readme_from_understanding(parsed_files: list[dict[str, Any]], repo_name: str = "") -> str:
    understanding = analyze_project(parsed_files)
    if not repo_name:
        repo_name = "Repository"
    sections: list[str] = [f"# {repo_name}"]

    overview = _render_overview(understanding)
    if overview:
        sections.append("## Overview\n" + overview)

    architecture = _render_architecture(understanding)
    if architecture:
        sections.append("## Architecture Flow\n" + architecture)

    structure = _render_structure(understanding)
    if structure:
        sections.append("## Project Structure\n" + structure)

    modules = _render_modules(understanding)
    if modules:
        sections.append("## Modules\n" + modules)

    if understanding["entrypoints"]:
        usage = _usage_for_entry(understanding["entrypoints"][0])
        if usage:
            sections.append("## Usage\n" + usage)

    return "\n\n".join(sections).strip() + "\n"


def create_onboarding_guide(parsed_files: list[dict[str, Any]], persona: str) -> str:
    understanding = analyze_project(parsed_files)
    top_files = sorted(
        understanding["files"],
        key=lambda x: (x.get("line_count", 0), len(x.get("functions", [])) + len(x.get("classes", []))),
        reverse=True,
    )[:8]
    first_files = "\n".join(f"- `{item['path']}` -> {_module_role(item)}" for item in top_files)
    flow = "\n".join(f"- {step}" for step in understanding["flow_steps"])
    return f"""# Onboarding Guide ({persona})

## First 30 Minutes
{first_files or '- Explore repository root files'}

## System Flow
{flow}

## Contribution Checklist
- Add tests for behavior changes.
- Keep docs aligned with real module behavior.
- Run static checks before opening a PR.
"""
