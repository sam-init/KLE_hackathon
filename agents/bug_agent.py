from __future__ import annotations

import re
from typing import Any

from agents.base_agent import AgentFinding, BaseAgent

class BugSafetyAgent(BaseAgent):
    name = "Bug & Safety"

    def analyze(self, parsed_files: list[dict[str, Any]], persona: str) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        lowered_persona = persona.strip().lower()
        for item in parsed_files:
            path = item["path"]
            lines = item["content"].splitlines()

            for i, line in enumerate(lines, start=1):
                # Unsafe dynamic code execution
                if re.search(r"\b(eval|exec)\s*\(", line):
                    finding = self._emit(
                        file=path, line=i,
                        issue_title="Unsafe Dynamic Code Execution",
                        explanation="Dynamic evaluation can execute untrusted input and cause runtime safety issues.",
                        severity="high",
                        fix_suggestion="Replace eval/exec with explicit parsing or a strict allow-list of supported operations.",
                        confidence=0.94,
                    )
                    if finding:
                        findings.append(finding)

                # Broad exception suppressed
                if "except Exception:" in line or "except:" in line:
                    # Look ahead for silent pass
                    lookahead = "\n".join(lines[i:i+2])
                    if "pass" in lookahead:
                        finding = self._emit(
                            file=path, line=i,
                            issue_title="Broad Exception Silently Ignored",
                            explanation="Catching Exception or bare except and silently passing hides production failures.",
                            severity="medium",
                            fix_suggestion="Catch specific exception types and at minimum log the error before handling.",
                            confidence=0.89,
                        )
                        if finding:
                            findings.append(finding)

                # Bare except (without Exception)
                if re.search(r"^except\s*:", line):
                    finding = self._emit(
                        file=path, line=i,
                        issue_title="Bare Except Clause",
                        explanation="A bare `except:` catches even system exits, masking critical errors.",
                        severity="high",
                        fix_suggestion="Catch specific exception classes (e.g., `except ValueError:`).",
                        confidence=0.93,
                    )
                    if finding:
                        findings.append(finding)

                # Return inside finally
                if "finally:" in line and i+1 < len(lines) and "return" in lines[i+1]:
                    finding = self._emit(
                        file=path, line=i+1,
                        issue_title="Return Inside Finally Block",
                        explanation="A return in finally destroys any exception information.",
                        severity="high",
                        fix_suggestion="Avoid return/break/continue in finally; restructure the try-except logic.",
                        confidence=0.95,
                    )
                    if finding:
                        findings.append(finding)

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
                f.explanation += " Such bugs can be hard to debug later because they hide the real error."
                f.fix_suggestion += " Always log the exception details."
        return findings