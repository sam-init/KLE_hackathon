from __future__ import annotations

import re
from typing import Any

from agents.base_agent import AgentFinding, BaseAgent


class SecurityAgent(BaseAgent):
    name = "Security"

    def analyze(self, parsed_files: list[dict[str, Any]], persona: str) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        lowered_persona = persona.strip().lower()

        # Keep patterns focused on high-signal issues to reduce noise.
        secret_pattern = re.compile(
            r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
        )
        jwt_none_alg_pattern = re.compile(r"(?i)\b(alg|algorithm)\b.{0,20}\bnone\b")
        weak_hash_pattern = re.compile(r"(?i)\b(md5|sha1)\b")
        dangerous_eval_pattern = re.compile(r"(?i)\b(eval|exec)\s*\(")

        for item in parsed_files:
            path = item.get("path", "")
            lines = item.get("content", "").splitlines()
            for i, line in enumerate(lines, start=1):
                if secret_pattern.search(line):
                    finding = self._emit(
                        file=path,
                        line=i,
                        issue_title="Potential Hardcoded Secret",
                        explanation="Credential-like values appear directly in source code.",
                        severity="critical",
                        fix_suggestion=(
                            "Move secrets to environment variables or a secret manager and rotate any exposed key."
                        ),
                        confidence=0.9,
                    )
                    if finding:
                        findings.append(finding)

                if "subprocess" in line and "shell=True" in line:
                    finding = self._emit(
                        file=path,
                        line=i,
                        issue_title="Command Execution With shell=True",
                        explanation="Using shell=True can enable command injection if arguments are user-influenced.",
                        severity="high",
                        fix_suggestion="Pass command arguments as a list and avoid shell=True.",
                        confidence=0.92,
                    )
                    if finding:
                        findings.append(finding)

                if dangerous_eval_pattern.search(line):
                    finding = self._emit(
                        file=path,
                        line=i,
                        issue_title="Dynamic Code Execution Detected",
                        explanation="eval/exec on dynamic input can lead to arbitrary code execution.",
                        severity="high",
                        fix_suggestion="Replace dynamic evaluation with explicit parsing/dispatch logic.",
                        confidence=0.9,
                    )
                    if finding:
                        findings.append(finding)

                if jwt_none_alg_pattern.search(line):
                    finding = self._emit(
                        file=path,
                        line=i,
                        issue_title="JWT Algorithm 'none' Usage",
                        explanation="Accepting 'none' algorithm disables signature verification and can bypass auth.",
                        severity="critical",
                        fix_suggestion="Explicitly allow only signed algorithms (for example RS256/HS256).",
                        confidence=0.95,
                    )
                    if finding:
                        findings.append(finding)

                if weak_hash_pattern.search(line) and any(x in line.lower() for x in ("password", "token", "auth")):
                    finding = self._emit(
                        file=path,
                        line=i,
                        issue_title="Weak Hash Used For Sensitive Data",
                        explanation="MD5/SHA1 are weak for security-sensitive use cases.",
                        severity="medium",
                        fix_suggestion="Use a modern hash strategy (bcrypt/argon2 for passwords, SHA-256/HMAC where appropriate).",
                        confidence=0.86,
                    )
                    if finding:
                        findings.append(finding)

        deduped = self._dedupe(findings)
        return self._apply_persona_tone(deduped, lowered_persona)[:10]

    @staticmethod
    def _dedupe(findings: list[AgentFinding]) -> list[AgentFinding]:
        seen: set[tuple[str, int, str]] = set()
        out: list[AgentFinding] = []
        for f in findings:
            key = (f.file, f.line, f.issue_title)
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
        return out

    @staticmethod
    def _apply_persona_tone(findings: list[AgentFinding], persona: str) -> list[AgentFinding]:
        if "intern" in persona or "student" in persona:
            for f in findings:
                f.explanation = (
                    f"{f.explanation} Why this matters: attackers can turn this into unauthorized access or data exposure."
                )
        elif "frontend" in persona:
            for f in findings:
                if "xss" not in f.explanation.lower():
                    f.fix_suggestion = f"{f.fix_suggestion} Also verify user-visible surfaces are safely encoded."
        return findings
