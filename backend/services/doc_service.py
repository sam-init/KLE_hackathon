from __future__ import annotations

import logging
from typing import Any

from backend.services.nim_client import NIMClient
from backend.services.persona import persona_style
from backend.services.structure_service import StructureService
from backend.utils.settings import settings
from docs.graph_builder import build_dependency_graph, build_execution_flowchart, build_knowledge_graph
from docs.readme_generator import create_onboarding_guide, create_readme_template
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

        existing_docs = "\n\n".join(item["content"] for item in parsed_files if item["path"].endswith(".md"))
        doc_rot = detect_doc_rot(parsed_files, existing_docs)
        if doc_rot:
            logger.info("Docs phase | doc_rot_detected=true regenerating_readme")
            readme = await self._generate_readme(parsed_files, persona, structure_context, regenerate=True, repo_name=repo_name)

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
        base = create_readme_template(parsed_files, persona, repo_name=repo_name)
        action = "Regenerated due to doc rot detection." if regenerate else "Generated from current repository state."

        # Build a rich facts block with real symbol names for the NIM prompt
        all_fns = []
        all_classes = []
        for item in parsed_files[:15]:
            for fn in item.get("functions", [])[:3]:
                all_fns.append(f"`{fn['name']}` in {item['path']}")
            for cls in item.get("classes", [])[:2]:
                all_classes.append(f"`{cls['name']}` in {item['path']}")

        real_fns = ", ".join(all_fns[:12]) or "none detected"
        real_classes = ", ".join(all_classes[:8]) or "none detected"
        file_list = ", ".join(item["path"] for item in parsed_files[:10])

        prompt = f"""
        You are writing a README.md for the repository: **{repo_name or 'this project'}**.

        REAL CODE FACTS (use these specifically — do not make things up):
        - Files: {file_list}
        - Real functions found: {real_fns}
        - Real classes found: {real_classes}
        - Structure: {structure_context}
        - Context: {action}

        PERSONA: {persona_style(persona)}

        TASK: Rewrite the template below into a polished, specific README.md.
        - Use the actual function and class names found in the code
        - Keep all paths repo-relative only
        - Never include render/workspace/temp absolute paths
        - If data is missing, omit that detail instead of fabricating
        - Usage must only include runnable examples if entrypoints are explicit
        - Architecture must describe only relationships inferable from imports and symbols
        - Output clean GitHub-flavored Markdown only — no extra commentary

        TEMPLATE TO REWRITE:
        {base}
        """.strip()

        generated = await self.nim.chat(
            model=settings.nim_model_qwen_docs,
            system_prompt="You are a senior technical writer producing real, repo-specific documentation. Never use placeholder text.",
            user_prompt=prompt,
            temperature=0.2,
        )
        return generated or base

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
