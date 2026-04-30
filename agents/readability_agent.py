from __future__ import annotations

import ast
from typing import Any

from agents.base_agent import AgentFinding, BaseAgent

class ReadabilityDocsAgent(BaseAgent):
    name = "Readability & Docs"

    def analyze(self, parsed_files: list[dict[str, Any]], persona: str) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        lowered_persona = persona.strip().lower()
        for item in parsed_files:
            if not item["path"].endswith(".py"):
                continue
            path = item["path"]
            code = item["content"]
            lines = code.splitlines()

            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                # Missing docstring on non-trivial function
                if isinstance(node, ast.FunctionDef):
                    if len(node.body) > 3 and ast.get_docstring(node) is None:
                        findings.append(self._emit(
                            file=path, line=node.lineno,
                            issue_title="Missing Function Docstring",
                            explanation="Non‑trivial function lacks a docstring, reducing understandability.",
                            severity="low",
                            fix_suggestion="Add a short docstring describing inputs, outputs, and side effects.",
                            confidence=0.76,
                        ))

                # Too many local variables (cognitive complexity)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    local_vars = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
                    if len(local_vars) > 15:
                        findings.append(self._emit(
                            file=path, line=node.lineno,
                            issue_title="Too Many Local Variables",
                            explanation=f"Function '{node.name}' has {len(local_vars)} local variables, increasing cognitive load.",
                            severity="low",
                            fix_suggestion="Break the function into smaller, focused pieces or group related data into a data class.",
                            confidence=0.77,
                        ))

                # Magic numbers (simplified: constant numeric literals not named)
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    # Skip 0, 1, -1, and small common numbers in certain contexts; very rough
                    if node.value not in (0, 1, -1) and not isinstance(node.parent, ast.Compare):
                        pass  # too many false positives; skip for now

            # Long lines (outside AST)
            for i, line in enumerate(lines, start=1):
                if len(line) > 140:
                    findings.append(self._emit(
                        file=path, line=i,
                        issue_title="Very Long Line",
                        explanation="Lines longer than 140 characters are harder to read and review.",
                        severity="low",
                        fix_suggestion="Break long expressions across multiple lines with clear naming.",
                        confidence=0.78,
                    ))

        findings = [f for f in findings if f is not None]
        return self._apply_persona_tone(self._dedupe(findings), lowered_persona)

    @staticmethod
    def _dedupe(findings):
        seen = set()
        out = []
        for f in findings:
            key = (f.file, f.line, f.issue_title)
            if key not in seen:
                seen.add(key)
                out.append(f)
        return out

    @staticmethod
    def _apply_persona_tone(findings, persona):
        for f in findings:
            if "intern" in persona or "student" in persona:
                f.explanation += " Clear code helps your team and future you understand the logic faster."
                f.fix_suggestion += " Think of docstrings as mini‑instructions for the next developer."
        return findings