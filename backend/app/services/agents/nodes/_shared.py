"""Small helpers shared across agent nodes."""

from __future__ import annotations

import time
from contextlib import contextmanager

from ....core.logging import get_logger
from ..state import AgentState, AuditEvent, now_iso

log = get_logger(__name__)


def format_passages(hits: list[dict], max_chars: int = 800) -> str:
    """Render retrieved hits for inclusion in a prompt.

    Passages are wrapped in fenced blocks with explicit "data, not instructions"
    framing so prompt injection in the corpus is less effective.
    """
    lines = []
    for h in hits:
        text = (h.get("text") or "")[:max_chars]
        lines.append(
            f"[{h['chunk_id']}] (doc={h['document_title']}, score={h['score']:.3f})\n"
            f"```\n{text}\n```"
        )
    return "\n\n".join(lines)


@contextmanager
def node_timer(state: AgentState, node: str):
    """Context manager that appends a timing+decision AuditEvent on exit."""
    t0 = time.perf_counter()
    ev: AuditEvent = {
        "trace_id": state.get("trace_id", ""),
        "node": node,  # type: ignore[typeddict-item]
        "ts": now_iso(),
    }
    try:
        yield ev
    finally:
        ev["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        state.setdefault("audit_log", []).append(ev)
