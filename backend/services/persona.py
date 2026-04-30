from __future__ import annotations

PERSONA_GUIDANCE = {
    "Intern": "Explain each finding in simple language and include one practical next action.",
    "Student": "Clarify concept-level reasoning and connect each fix to software engineering fundamentals.",
    "Frontend Developer": "Prioritize UX, component boundaries, API contracts, and accessibility implications.",
    "Backend Developer": "Prioritize correctness, architecture, performance bottlenecks, and scalability trade-offs.",
}


def persona_style(persona: str) -> str:
    return PERSONA_GUIDANCE.get(persona, PERSONA_GUIDANCE["Student"])
