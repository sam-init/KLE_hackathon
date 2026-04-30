from __future__ import annotations

import logging
import re
from typing import Any

from backend.services.nim_client import NIMClient
from backend.services.persona import persona_style
from backend.services.structure_service import StructureService
from backend.utils.settings import settings
from docs.graph_builder import build_dependency_graph, build_execution_flowchart, build_knowledge_graph
from docs.readme_generator import create_onboarding_guide, create_readme_from_understanding
from docs.rot_detector import detect_doc_rot
from rag.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)


class DocumentationService:
    def __init__(self, rag: RAGPipeline) -> None:
        self.rag = rag
        self.nim = NIMClient()
        self.structure = StructureService()

    async def generate(self, parsed_files: list[dict[str, Any]], persona: str, repo_name: str = "") -> dict[str, Any]:
        logger.info("Docs pipeline started | files=%d persona=%s repo=%s", len(parsed_files), persona, repo_name or "unknown")
        index_stats = self.rag.index_repository(parsed_files)
        structure_context = await self.structure.derive(parsed_files)

        logger.info("Docs phase | generating_docstrings")
        docstrings = self._generate_docstrings(parsed_files, persona)
        logger.info("Docs phase | generating_readme")
        readme = await self._generate_readme(parsed_files, persona, structure_context, repo_name=repo_name)
        existing_readme = next((item.get("content", "") for item in parsed_files if item.get("path", "").lower().endswith("readme.md")), "")

        existing_docs = "\n\n".join(item["content"] for item in parsed_files if item["path"].endswith(".md"))
        doc_rot = detect_doc_rot(parsed_files, existing_docs)
        if doc_rot:
            logger.info("Docs phase | doc_rot_detected=true regenerating_readme")
            readme = await self._generate_readme(parsed_files, persona, structure_context, regenerate=True, repo_name=repo_name)
        if not existing_readme.strip():
            logger.info("README status | mode=new_generated")
        elif existing_readme.strip() == readme.strip():
            logger.info("README status | mode=unchanged_from_existing")
        else:
            logger.info("README status | mode=updated_from_existing")

        logger.info("Docs phase | building_modular_docs_and_graphs")
        modular_docs = self._build_modular_docs(parsed_files, persona)

        logger.info("Docs pipeline completed | files=%d persona=%s", len(parsed_files), persona)
        return {
            "docstrings": docstrings,
            "readme": readme,
            "modular_docs": modular_docs,
            "onboarding_guide": create_onboarding_guide(parsed_files, persona),
            "dependency_graph": build_dependency_graph(parsed_files),
            "execution_flowchart": build_execution_flowchart(parsed_files),
            "knowledge_graph": build_knowledge_graph(parsed_files),
            "doc_rot_detected": doc_rot,
            "metadata": {"rag": index_stats, "nim_enabled": self.nim.enabled, "structure": structure_context},
        }

    def _generate_docstrings(self, parsed_files: list[dict[str, Any]], persona: str) -> dict[str, str]:
        output: dict[str, str] = {}
        for item in parsed_files:
            blocks = []
            for fn in item.get("functions", [])[:25]:
                args = ", ".join(fn.get("args", [])) if fn.get("args") else "args"
                imports = ", ".join(item.get("imports", [])[:4]) or "none"
                blocks.append(
                    f"{fn['name']} (line {fn['line']}):\n"
                    f"\"\"\"{fn['name']} in `{item['path']}` (around line {fn['line']}) performs a targeted operation "
                    f"within the {item['language']} module context.\n\n"
                    f"Args:\n"
                    f"    {args}: Parameters consumed by this function.\n\n"
                    f"Context:\n"
                    f"    Imports used in this module include: {imports}.\n\n"
                    f"Returns:\n"
                    f"    Output produced by `{fn['name']}` for downstream callers.\n\"\"\""
                )
            if blocks:
                output[item["path"]] = "\n\n".join(blocks)

        if not output:
            output["project"] = "No functions detected in supported language parsers."

        return output

    async def _generate_readme(
        self,
        parsed_files: list[dict[str, Any]],
        persona: str,
        structure_context: dict[str, Any],
        regenerate: bool = False,
        repo_name: str = "",
    ) -> str:
        base = create_readme_from_understanding(parsed_files, repo_name=repo_name)
        if not self.nim.enabled:
            logger.info("README generation source | source=deterministic_draft reason=nim_disabled")
            return base

        top_files = parsed_files[:16]
        route_hits: list[str] = []
        symbol_hits: list[str] = []
        for item in top_files:
            path = item.get("path", "")
            content = item.get("content", "")
            for line in content.splitlines()[:300]:
                stripped = line.strip()
                if re.search(r"@app\.(route|get|post|put|patch|delete)\(", stripped):
                    route_hits.append(f"{path}: {stripped}")
            for fn in item.get("functions", [])[:4]:
                name = str(fn.get("name", "")).strip()
                if name:
                    symbol_hits.append(f"{path}:{name}")

        facts_block = "\n".join(
            [
                f"- files: {', '.join(item.get('path', '') for item in top_files[:10])}",
                f"- symbols: {', '.join(symbol_hits[:16]) or 'none'}",
                f"- route decorators: {', '.join(route_hits[:10]) or 'none'}",
            ]
        )

        # LLM-led rewrite with strict grounding constraints.
        prompt = f"""
Write a polished repository README.
Hard requirements:
- Stay strictly grounded in provided code facts and draft README.
- In the first 2 sentences, explain WHAT this project does for a user/operator (not what files exist).
- Mention at least two concrete code references (function names, endpoints, or modules).
- Keep all file paths repo-relative.
- Do not add frameworks/tools not present.
- Avoid generic filler text.
- Keep sections concise and developer-focused.
- If information is missing, omit that detail.

Persona: {persona_style(persona)}
Structure context (for clarity only): {structure_context}
Regeneration reason: {"doc_rot" if regenerate else "normal"}
Code facts:
{facts_block}

README DRAFT:
{base}
""".strip()
        generated = await self.nim.chat(
            model=settings.nim_model_qwen_docs,
            system_prompt="You are a senior engineer editing README text for accuracy and clarity. Never hallucinate.",
            user_prompt=prompt,
            temperature=0.1,
        )
        if generated and generated.strip():
            logger.info("README generation source | source=llm_rewrite")
            return generated
        logger.info("README generation source | source=deterministic_draft reason=llm_empty")
        return base

    def _build_modular_docs(self, parsed_files: list[dict[str, Any]], persona: str) -> dict[str, str]:
        modules: dict[str, str] = {}
        for item in parsed_files:
            symbols = []
            for fn in item.get("functions", [])[:8]:
                symbols.append(f"- function `{fn['name']}` at line {fn['line']}")
            for cls in item.get("classes", [])[:6]:
                symbols.append(f"- class `{cls['name']}` at line {cls['line']}")
            symbol_block = "\n".join(symbols) or "- no parsed symbols"
            imports = ", ".join(item.get("imports", [])[:12]) or "None"
            modules[item["path"]] = (
                f"Module: {item['path']}\n"
                f"Language: {item['language']}\n"
                f"Size: {item.get('line_count', 0)} lines\n"
                f"Functions: {len(item.get('functions', []))}\n"
                f"Classes: {len(item.get('classes', []))}\n"
                f"Imports: {imports}\n"
                f"Key symbols:\n{symbol_block}\n"
                f"Persona note: {persona_style(persona)}\n"
                f"Suggested next read: start at line 1, then jump to the listed symbols."
            )
        return modules
