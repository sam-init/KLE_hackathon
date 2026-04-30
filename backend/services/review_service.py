from __future__ import annotations

import json
import logging
from typing import Any

from agents.base_agent import AgentFinding, SEVERITY_ORDER
from agents.orchestrator import ReviewOrchestrator
from backend.services.nim_client import NIMClient
from backend.services.persona import persona_style
from backend.services.review_prompts import AGENT_PROMPTS, COMMON_CONSTRAINTS, JSON_SCHEMA_GUIDE
from backend.services.structure_service import StructureService
from backend.utils.settings import settings
from rag.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, rag: RAGPipeline) -> None:
        self.rag = rag
        self.orchestrator = ReviewOrchestrator()
        self.nim = NIMClient()
        self.structure = StructureService()

    async def review(self, parsed_files: list[dict[str, Any]], persona: str) -> dict[str, Any]:
        logger.info("Review pipeline started | files=%d persona=%s", len(parsed_files), persona)
        index_stats = self.rag.index_repository(parsed_files)
        structure_context = await self.structure.derive(parsed_files)
        logger.info("Review phase | running_rule_based_agents")
        findings = self.orchestrator.run(parsed_files, persona)
        logger.info("Review phase | running_llm_agents")
        findings.extend(await self._qwen_review_pass(parsed_files, persona))
        findings = self._dedupe_findings(findings)
        findings = self._apply_persona(findings, persona)
        logger.info("Review phase | summarizing_findings count=%d", len(findings))

        summary = await self._summarize_findings(findings, persona, structure_context)
        logger.info("Review pipeline completed | findings=%d persona=%s", len(findings), persona)
        return {
            "findings": [f.__dict__ for f in findings],
            "summary": summary,
            "reviewed_files": [item["path"] for item in parsed_files],
            "metadata": {
                "rag": index_stats,
                "agent_count": len(self.orchestrator.agents),
                "nim_enabled": self.nim.enabled,
                "structure": structure_context,
            },
        }

    async def _summarize_findings(self, findings: list[Any], persona: str, structure_context: dict[str, Any]) -> str:
        if not findings:
            return "No high-confidence issues were detected. The current changes appear stable under configured review checks."

        top = findings[:8]
        bullet_lines = "\n".join(
            f"- [{item.severity.upper()}] {item.issue_title} in {item.file}:{item.line} ({item.agent})"
            for item in top
        )

        prompt = f"""
Persona guidance: {persona_style(persona)}
Create an industrial, concise code review summary with priorities and immediate next actions.
Findings:
{bullet_lines}
Structure context:
{json.dumps(structure_context)}
""".strip()

        generated = await self.nim.chat(
            model=settings.nim_model_qwen_review,
            system_prompt="You are a senior staff engineer producing PR review summaries.",
            user_prompt=prompt,
            temperature=0.1,
        )

        if generated:
            return generated

        return f"Priority issues detected across code quality checks:\n{bullet_lines}\n\nNext step: resolve critical/high findings first, then medium findings that impact maintainability and scale."

    async def _qwen_review_pass(self, parsed_files: list[dict[str, Any]], persona: str) -> list[AgentFinding]:
        if not self.nim.enabled:
            return []

        all_findings: list[AgentFinding] = []

        for agent_prompt in AGENT_PROMPTS:
            sample = self._build_sample(parsed_files, agent_prompt.name)
            prompt = f"""
Persona: {persona}
Agent: {agent_prompt.name}
Focus: {agent_prompt.focus}
Task instructions:
{agent_prompt.instructions}

{COMMON_CONSTRAINTS}

Additional strict rules:
- confidence must be >= 0.75
- explanation max 3 sentences
- fix_suggestion must be concrete and implementable
- set agent to "{agent_prompt.name}"

{JSON_SCHEMA_GUIDE}

Code input:
{json.dumps(sample)}
""".strip()

            out = await self.nim.chat(
                model=settings.nim_model_qwen_review,
                system_prompt="You are an industrial static code review agent. Return JSON array only.",
                user_prompt=prompt,
                temperature=0.0,
            )
            if not out:
                continue

            parsed = self._parse_json_array(out)
            all_findings.extend(self._coerce_findings(parsed, fallback_agent=agent_prompt.name))

        return all_findings

    def _coerce_findings(self, parsed: list[dict[str, Any]], fallback_agent: str) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        for item in parsed:
            try:
                confidence = float(item.get("confidence", 0))
                if confidence < 0.75:
                    continue
                severity = str(item.get("severity", "medium")).lower()
                if severity not in {"low", "medium", "high", "critical"}:
                    severity = "medium"
                findings.append(
                    AgentFinding(
                        file=str(item["file"]),
                        line=max(1, int(item["line"])),
                        issue_title=str(item["issue_title"]),
                        explanation=str(item["explanation"]),
                        severity=severity,
                        fix_suggestion=str(item["fix_suggestion"]),
                        confidence=confidence,
                        agent=str(item.get("agent", fallback_agent)),
                    )
                )
            except Exception:
                continue
        return findings

    def _build_sample(self, parsed_files: list[dict[str, Any]], focus_name: str) -> list[dict[str, str]]:
        focus_query = f"{focus_name} code risks, vulnerabilities, defects, anti-patterns"
        context_hits = self.rag.retrieve(focus_query, k=10)

        by_path: dict[str, list[str]] = {}
        for hit in context_hits:
            path = hit.get("path", "")
            if not path:
                continue
            by_path.setdefault(path, [])
            by_path[path].append(hit.get("text", ""))

        sample: list[dict[str, str]] = []
        for path, snippets in by_path.items():
            merged = "\n".join(snippets)[:7000]
            sample.append({"path": path, "snippet": merged})

        if sample:
            return sample[:8]

        fallback: list[dict[str, str]] = []
        for item in parsed_files[:8]:
            lines = item.get("content", "").splitlines()
            snippet = "\n".join(lines[:220])
            fallback.append({"path": item["path"], "snippet": snippet})
        return fallback

    def _parse_json_array(self, text: str) -> list[dict[str, Any]]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    def _dedupe_findings(self, findings: list[Any]) -> list[Any]:
        seen = set()
        unique = []
        for f in findings:
            key = (f.file, f.line, f.issue_title)
            if key in seen:
                continue
            seen.add(key)
            unique.append(f)
        unique.sort(key=lambda x: (SEVERITY_ORDER.get(x.severity, 0), x.confidence), reverse=True)
        return unique[:40]

    def _apply_persona(self, findings: list[AgentFinding], persona: str) -> list[AgentFinding]:
        for finding in findings:
            if persona == "Intern":
                finding.explanation = (
                    f"{finding.explanation} Why this matters: this pattern can cause bugs that are hard to debug later."
                )
            elif persona == "Student":
                finding.explanation = (
                    f"{finding.explanation} Concept: this relates to maintainability and correctness under change."
                )
            elif persona == "Frontend Developer":
                finding.fix_suggestion = (
                    f"{finding.fix_suggestion} Prioritize user impact, component clarity, and accessibility behavior."
                )
            elif persona == "Backend Developer":
                finding.fix_suggestion = (
                    f"{finding.fix_suggestion} Prioritize reliability, performance, and service boundary clarity."
                )
        return findings
