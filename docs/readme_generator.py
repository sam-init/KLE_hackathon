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


def _extract_capabilities(parsed_files: list[dict[str, Any]]) -> list[str]:
    capabilities: list[str] = []
    joined_content = "\n".join(str(item.get("content", ""))[:4000] for item in parsed_files[:20]).lower()
    paths = " ".join(item["path"].lower() for item in parsed_files)
    if "@app.route" in joined_content or "flask" in joined_content or "fastapi" in joined_content:
        capabilities.append("exposes web/API endpoints")
    if "/api/" in paths or "controller" in paths or "route" in paths:
        capabilities.append("handles request routing and response orchestration")
    if "validate" in joined_content or "validator" in paths:
        capabilities.append("validates and sanitizes input data")
    if "mapper" in paths or "intent" in paths:
        capabilities.append("maps domain intents or rules into executable actions")
    if "recon" in paths or "passive" in paths or "google" in paths:
        capabilities.append("runs reconnaissance/data-collection style workflows")
    if ".js" in paths or "static/" in paths or "frontend/" in paths:
        capabilities.append("includes a browser-facing UI layer")
    return list(dict.fromkeys(capabilities))


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
    runtime_hints = [h for h in hints if h != "dependency visualization"]
    if not runtime_hints:
        return "The repository coordinates domain modules to process inputs and produce actionable outputs."
    joined = ", ".join(dict.fromkeys(runtime_hints))
    return f"The system is built around {joined}, inferred from module names, symbols, and imports."


def _rank_core_modules(parsed_files: list[dict[str, Any]], max_items: int = 5) -> list[dict[str, Any]]:
    return sorted(
        parsed_files,
        key=lambda x: (
            len(x.get("imports", [])) * 2 + len(x.get("functions", [])) + len(x.get("classes", [])),
            x.get("line_count", 0),
        ),
        reverse=True,
    )[:max_items]


def _overview_narrative(understanding: dict[str, Any]) -> str:
    entry = understanding["entrypoints"][0]["path"] if understanding["entrypoints"] else ""
    core = _rank_core_modules(understanding["files"], max_items=4)
    core_paths = [f"`{item['path']}`" for item in core]
    module_part = ", ".join(core_paths) if core_paths else "detected modules"

    steps = understanding["flow_steps"]
    flow_hint = " -> ".join(step.replace("`", "") for step in steps[:4]) if steps else ""
    capabilities = understanding.get("capabilities", [])
    capability_text = ""
    if capabilities:
        capability_text = " Key behavior includes: " + "; ".join(capabilities[:4]) + "."
    if entry and flow_hint:
        return (
            f"The primary runtime entry is `{entry}`. It coordinates core modules such as {module_part}. "
            f"At runtime, the main flow is: {flow_hint}.{capability_text}"
        )
    if entry:
        return f"The primary runtime entry is `{entry}`. It coordinates logic across {module_part}.{capability_text}"
    return f"This codebase centers on {module_part}, with behavior inferred from imports, paths, and symbol relationships.{capability_text}"


def _group_paths(paths: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for path in sorted(paths):
        folder = path.split("/", 1)[0] if "/" in path else "root"
        groups.setdefault(folder, []).append(path)
    return groups


def _module_role(item: dict[str, Any]) -> str:
    p = item["path"].lower()
    base = PurePosixPath(p).name
    fn_count = len(item.get("functions", []))
    cls_count = len(item.get("classes", []))
    imports = " ".join(str(x).lower() for x in item.get("imports", []))
    if base in {"main.py", "app.py", "server.py", "manage.py", "index.ts", "index.js"} or "fastapi" in imports or "flask" in imports:
        return "Entry or orchestration module."
    if p.startswith("frontend/") or p.startswith("static/") or p.endswith((".tsx", ".jsx")) or "react" in imports:
        return "Frontend/UI module."
    if any(k in p for k in ("route", "controller", "api")):
        return "Request/response boundary module."
    if any(k in p for k in ("service", "agent", "orchestrator", "pipeline")):
        return "Processing/service logic."
    if any(k in p for k in ("parser", "loader", "ingest")):
        return "Ingestion/parsing module."
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
        "capabilities": _extract_capabilities(files),
        "groups": groups,
        "graph": graph,
        "entrypoints": entry,
        "flow_steps": flow_steps,
    }


def _render_overview(understanding: dict[str, Any]) -> str:
    lang_line = ", ".join(f"{k}: {v}" for k, v in understanding["languages"].items()) or "unknown"
    project_types = ", ".join(understanding["project_types"])
    narrative = _overview_narrative(understanding)
    return (
        f"{narrative}\n\n"
        f"{understanding['purpose']}\n\n"
        f"Project type: {project_types}\n"
        f"Language profile: {lang_line}"
    )


def _render_architecture(understanding: dict[str, Any]) -> str:
    steps: list[str] = understanding["flow_steps"]
    if not steps:
        return ""
    module_graph: dict[str, set[str]] = understanding["graph"]
    hub_modules = sorted(module_graph.items(), key=lambda x: len(x[1]), reverse=True)[:4]
    flow_lines = [f"{idx + 1}. {step}" for idx, step in enumerate(steps)]
    if hub_modules:
        flow_lines.append("")
        flow_lines.append("Module interaction hotspots:")
        for src, targets in hub_modules:
            if not targets:
                continue
            sample = ", ".join(f"`{t}`" for t in sorted(targets)[:3])
            flow_lines.append(f"- `{src}` imports/depends on {sample}")
    return "\n".join(flow_lines)


def _render_key_features(understanding: dict[str, Any]) -> str:
    lines: list[str] = []
    for item in _rank_core_modules(understanding["files"], max_items=6):
        symbols = [str(f.get("name", "")) for f in item.get("functions", [])[:2] if f.get("name")]
        if not symbols:
            continue
        lines.append(f"- `{item['path']}` implements `{', '.join(symbols)}`")
    return "\n".join(lines[:6])


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
        if item["path"].lower().endswith((".md", ".txt", ".json", ".yaml", ".yml")):
            continue
        fns = [str(f.get("name")) for f in item.get("functions", [])[:3] if f.get("name")]
        cls = [str(c.get("name")) for c in item.get("classes", [])[:2] if c.get("name")]
        sym = ", ".join([*(f"`{x}`" for x in cls), *(f"`{x}()`" for x in fns)])
        extras = f" Key symbols: {sym}." if sym else ""
        imports = ", ".join(item.get("imports", [])[:3]) if item.get("imports") else ""
        import_note = f" Imports: {imports}." if imports else ""
        lines.append(f"- **`{item['path']}`**: {_module_role(item)}{extras}{import_note}")
    return "\n".join(lines)


def _usage_for_entry(entry: dict[str, Any]) -> str:
    path = entry["path"]
    lower = path.lower()
    imports = " ".join(str(x).lower() for x in entry.get("imports", []))
    if lower.endswith(".py"):
        module = PurePosixPath(path).stem
        if "flask" in imports:
            return f"```bash\nexport FLASK_APP={module}\nflask run\n```"
        if "fastapi" in imports or "uvicorn" in imports:
            return f"```bash\nuvicorn {module}:app --reload\n```"
        return f"```bash\npython {path}\n```"
    if lower.endswith(".js"):
        return f"```bash\nnode {path}\n```"
    if lower.endswith(".ts"):
        return f"```bash\nnpx ts-node {path}\n```"
    if lower.endswith((".v", ".sv")):
        return f"```text\nUse your HDL simulator/synthesis tool with entry file: {path}\n```"
    return ""


def _render_getting_started(understanding: dict[str, Any]) -> str:
    langs = understanding["languages"]
    steps: list[str] = []
    if "py" in langs:
        steps.append("- Python 3.10+")
        steps.append("- Install dependencies with `pip install -r requirements.txt` (if present)")
    if "js" in langs or "ts" in langs or "tsx" in langs:
        steps.append("- Node.js 18+")
        steps.append("- Install dependencies with `npm install` (if `package.json` exists)")
    if "v" in langs or "sv" in langs:
        steps.append("- Verilog/SystemVerilog simulator or synthesis toolchain")
    return "\n".join(steps)


def _render_built_with(understanding: dict[str, Any]) -> str:
    imports_joined = " ".join(
        str(imp).lower()
        for item in understanding["files"]
        for imp in item.get("imports", [])
    )
    labels: list[str] = []
    if "fastapi" in imports_joined:
        labels.append("- FastAPI")
    if "flask" in imports_joined:
        labels.append("- Flask")
    if "django" in imports_joined:
        labels.append("- Django")
    if "react" in imports_joined:
        labels.append("- React")
    if "next" in imports_joined:
        labels.append("- Next.js")
    if "pydantic" in imports_joined:
        labels.append("- Pydantic")
    langs = understanding["languages"]
    if "py" in langs:
        labels.append("- Python")
    if "js" in langs:
        labels.append("- JavaScript")
    if "ts" in langs or "tsx" in langs:
        labels.append("- TypeScript")
    if "v" in langs or "sv" in langs:
        labels.append("- Verilog/SystemVerilog")
    deduped = list(dict.fromkeys(labels))
    return "\n".join(deduped[:10])


def _render_installation(understanding: dict[str, Any]) -> str:
    langs = understanding["languages"]
    lines: list[str] = ["```bash", "git clone <repo-url>", "cd <repo-folder>"]
    if "py" in langs:
        lines.append("pip install -r requirements.txt  # if present")
    if "js" in langs or "ts" in langs or "tsx" in langs:
        lines.append("npm install  # if package.json is present")
    lines.append("```")
    return "\n".join(lines)


def _render_license(understanding: dict[str, Any]) -> str:
    for item in understanding["files"]:
        base = PurePosixPath(item["path"]).name.lower()
        if base in {"license", "license.txt", "license.md", "copying"}:
            return f"See `{item['path']}`."
    return ""


def _render_how_it_works(understanding: dict[str, Any]) -> str:
    steps = understanding["flow_steps"]
    if not steps:
        return ""
    normalized = [s.replace("entrypoint:", "entry") for s in steps]
    return "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(normalized))


def create_readme_from_understanding(parsed_files: list[dict[str, Any]], repo_name: str = "") -> str:
    understanding = analyze_project(parsed_files)
    if not repo_name:
        repo_name = "Repository"
    sections: list[str] = [f"# {repo_name}"]

    overview = _render_overview(understanding)
    if overview:
        sections.append("## About The Project\n" + overview)

    built_with = _render_built_with(understanding)
    if built_with:
        sections.append("### Built With\n" + built_with)

    how_it_works = _render_how_it_works(understanding)
    if how_it_works:
        sections.append("## How It Works\n" + how_it_works)

    key_features = _render_key_features(understanding)
    if key_features:
        sections.append("## Key Features\n" + key_features)

    architecture = _render_architecture(understanding)
    if architecture:
        sections.append("## Architecture Flow\n" + architecture)

    structure = _render_structure(understanding)
    if structure:
        sections.append("## Project Structure\n" + structure)

    modules = _render_modules(understanding)
    if modules:
        sections.append("## Module Responsibilities\n" + modules)

    getting_started = _render_getting_started(understanding)
    if getting_started:
        sections.append("## Getting Started\n### Prerequisites\n" + getting_started)

    installation = _render_installation(understanding)
    if installation:
        sections.append("### Installation\n" + installation)

    if understanding["entrypoints"]:
        usage = _usage_for_entry(understanding["entrypoints"][0])
        if usage:
            sections.append("## Usage\n" + usage)

    sections.append(
        "## Contributing\n"
        "Contributions should include focused changes, tests for behavior updates, and synced documentation."
    )

    license_section = _render_license(understanding)
    if license_section:
        sections.append("## License\n" + license_section)

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
