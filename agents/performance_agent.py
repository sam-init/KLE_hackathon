from __future__ import annotations

import re
from typing import Any

from agents.base_agent import AgentFinding, BaseAgent

class PerformanceAgent(BaseAgent):
    name = "Performance"

    def analyze(self, parsed_files: list[dict[str, Any]], persona: str) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        lowered_persona = persona.strip().lower()
        for item in parsed_files:
            lines = item["content"].splitlines()
            path = item["path"]

            # Nested loops (using joined content)
            joined = "\n".join(lines)
            nested = re.search(r"for\s+.+\n(\s{2,}|\t)+for\s.+", joined)
            if nested:
                line = joined[:nested.start()].count("\n") + 1
                finding = self._emit(
                    file=path, line=line,
                    issue_title="Nested Loop Hot Path",
                    explanation="Nested loops can lead to O(n²) behavior on large input sets.",
                    severity="medium",
                    fix_suggestion="Consider indexing data structures (dict/set) or precomputing lookups.",
                    confidence=0.79,
                )
                if finding:
                    findings.append(finding)

            # I/O inside loop
            for i, line in enumerate(lines, start=1):
                if "for " in line and i < len(lines) and "open(" in lines[i]:
                    finding = self._emit(
                        file=path, line=i,
                        issue_title="File Open Inside Loop",
                        explanation="Opening files repeatedly inside a loop increases system call overhead.",
                        severity="medium",
                        fix_suggestion="Open file handles outside the loop or batch I/O operations.",
                        confidence=0.81,
                    )
                    if finding:
                        findings.append(finding)

                # String concatenation in loop (Python specific)
                if re.search(r"\w+\s*\+=\s*\w+", line) and "for " in line:
                    finding = self._emit(
                        file=path, line=i,
                        issue_title="Inefficient String Concatenation in Loop",
                        explanation="Repeated string concatenation creates many intermediate objects.",
                        severity="low",
                        fix_suggestion="Use list comprehension and `''.join()` or collect items in a list.",
                        confidence=0.75,
                    )
                    if finding:
                        findings.append(finding)

                # Repeated attribute access inside loop (simple pattern: for x in ...: x.attr)
                # could be flagged as potential slowdown if attr is a property? Hard; skip.

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
                f.explanation += " In performance-critical code, even small inefficiencies can add up."
                f.fix_suggestion += " Use a profiler to confirm the hot path."
        return findings