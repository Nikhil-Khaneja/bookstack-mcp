"""Input guardrails for user queries.

Deliberately modest: length caps, empty check, and a small set of
prompt-injection regexes. This is not a silver bullet — the real defense
for injection is the downstream prompt template (we always wrap retrieved
content in fenced blocks and give the model an explicit instruction to
ignore embedded instructions). The regex layer is a fast pre-filter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...core.config import get_settings
from ...core.errors import GuardrailViolation

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?previous instructions", re.IGNORECASE),
    re.compile(r"\byou are now\b", re.IGNORECASE),
    re.compile(r"^\s*system\s*:", re.IGNORECASE),
    re.compile(r"\bdeveloper mode\b", re.IGNORECASE),
    re.compile(r"disregard\b.{0,30}(instructions|context|above|prior|all)", re.IGNORECASE),
]


@dataclass(slots=True)
class ValidatedQuery:
    query: str
    flags: list[str]  # informative; injection is hard-blocked


def validate_input(query: str) -> ValidatedQuery:
    settings = get_settings()
    q = (query or "").strip()

    if not q:
        raise GuardrailViolation("query is empty")

    if len(q) > settings.max_query_chars:
        raise GuardrailViolation(
            f"query exceeds max length ({len(q)} > {settings.max_query_chars})"
        )

    flags: list[str] = []
    for p in _INJECTION_PATTERNS:
        if p.search(q):
            flags.append(f"injection:{p.pattern}")

    if flags:
        # Soft behavior: we *refuse* outright rather than try to scrub. Safer by default.
        raise GuardrailViolation(
            "query rejected by input guardrail",
            detail={"flags": flags},
        )

    return ValidatedQuery(query=q, flags=flags)
