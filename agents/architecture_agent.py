from __future__ import annotations

from typing import Any

from agents.base_agent import AgentFinding, BaseAgent

class ArchitectureAgent(BaseAgent):
    name = "Architecture"

    def analyze(self, parsed_files: list[dict[str, Any]], persona: str) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        lowered_persona = persona.strip().lower()
        for item in parsed_files:
            line_count = item.get("line_count", 0)
            fn_count = len(item.get("functions", []))
            classes = item.get("classes", [])
            class_count = len(classes)

            path = item["path"]

            if line_count > 650:
                findings.append(self._emit(
                    file=path, line=1,
                    issue_title="Oversized Module",
                    explanation="Large modules become difficult to reason about and test.",
                    severity="medium",
                    fix_suggestion="Split this module by domain responsibility and expose a slim interface layer.",
                    confidence=0.83,
                ))

            if fn_count > 35:
                findings.append(self._emit(
                    file=path, line=1,
                    issue_title="High Function Density",
                    explanation="Many functions in a single file suggests mixed responsibilities.",
                    severity="medium",
                    fix_suggestion="Group related functions into submodules by feature or abstraction layer.",
                    confidence=0.8,
                ))

            # New: too many classes in one file
            if class_count > 5:
                findings.append(self._emit(
                    file=path, line=1,
                    issue_title="Too Many Classes in One Module",
                    explanation="A module with many classes likely violates Single Responsibility Principle.",
                    severity="medium",
                    fix_suggestion="Distribute classes across separate modules that boundary domain concepts.",
                    confidence=0.78,
                ))

            # New: detect God Object (class with too many public methods)
            for cls in classes:
                methods = [m for m in cls.get("methods", []) if not m.startswith("_")]
                if len(methods) > 20:
                    findings.append(self._emit(
                        file=path, line=cls.get("start_line", 1),
                        issue_title=f"God Object — {cls['name']} Has {len(methods)} Public Methods",
                        explanation="A class with excessive public methods likely takes on too many responsibilities.",
                        severity="medium",
                        fix_suggestion="Extract cohesive subsets of behavior into collaborating classes.",
                        confidence=0.82,
                    ))

        # Filter out None from _emit
        findings = [f for f in findings if f is not None]
        findings = self._dedupe(findings)
        return self._apply_persona_tone(findings, lowered_persona)

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
                f.explanation += " Good modularity makes the code easier to understand and change."
                f.fix_suggestion += " Start by grouping related functions into a new module."
        return findings