from __future__ import annotations

import re
from typing import Any

from agents.base_agent import AgentFinding, BaseAgent

class AccessibilityAgent(BaseAgent):
    name = "Accessibility"

    def analyze(self, parsed_files: list[dict[str, Any]], persona: str) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        lowered_persona = persona.strip().lower()
        for item in parsed_files:
            path = item["path"]
            if not path.endswith((".tsx", ".jsx", ".html", ".js", ".ts")):
                continue
            lines = item["content"].splitlines()
            for i, line in enumerate(lines, start=1):
                # Image missing alt
                if re.search(r"<img\b", line, re.IGNORECASE) and "alt=" not in line:
                    finding = self._emit(
                        file=path,
                        line=i,
                        issue_title="Image Missing Alt Text",
                        explanation="Images without alt text reduce accessibility for screen reader users.",
                        severity="high",
                        fix_suggestion="Add a meaningful alt attribute describing content or use alt=\"\" for decorative images.",
                        confidence=0.93,
                    )
                    if finding:
                        findings.append(finding)

                # Clickable div without role
                if re.search(r"<div[^>]*\bonClick=", line, re.IGNORECASE) and "role=" not in line:
                    finding = self._emit(
                        file=path,
                        line=i,
                        issue_title="Clickable Div Without Role",
                        explanation="Interactive div elements should include semantic role and keyboard support.",
                        severity="medium",
                        fix_suggestion="Use a button element or add role, tabIndex, and keyboard handlers.",
                        confidence=0.88,
                    )
                    if finding:
                        findings.append(finding)

                # Input missing label association
                if re.search(r"<input\b", line, re.IGNORECASE) and "aria-label=" not in line and "aria-labelledby=" not in line:
                    # Only flag if no associated label nearby (simple heuristic: not preceded by <label> in same file)
                    pass  # complex to do line-by-line; skip for now

                # Link with no text (empty anchor)
                if re.search(r"<a\b[^>]*>\s*</a>", line, re.IGNORECASE):
                    finding = self._emit(
                        file=path,
                        line=i,
                        issue_title="Link Without Visible Text",
                        explanation="An empty link provides no context for screen reader users.",
                        severity="high",
                        fix_suggestion="Add descriptive text inside the link or use aria-label for screen-reader-only content.",
                        confidence=0.91,
                    )
                    if finding:
                        findings.append(finding)

                # Aria-labelledby pointing to missing id (simplified: flag any aria-labelledby without checking existence)
                if "aria-labelledby=" in line:
                    # Extract id and see if it appears elsewhere? too heavy; skip.
                    pass

        return self._apply_persona_tone(self._dedupe(findings), lowered_persona)

    @staticmethod
    def _dedupe(findings: list[AgentFinding]) -> list[AgentFinding]:
        seen = set()
        out = []
        for f in findings:
            key = (f.file, f.line, f.issue_title)
            if key not in seen:
                seen.add(key)
                out.append(f)
        return out

    @staticmethod
    def _apply_persona_tone(findings: list[AgentFinding], persona: str) -> list[AgentFinding]:
        for f in findings:
            if "intern" in persona or "student" in persona:
                f.explanation += " Why this matters: accessible sites work for everyone, including people using assistive technology."
                f.fix_suggestion += " (WCAG 2.1 guideline)"
            elif "frontend" in persona:
                f.fix_suggestion += " Remember to test with a screen reader (e.g., NVDA/VoiceOver)."
        return findings