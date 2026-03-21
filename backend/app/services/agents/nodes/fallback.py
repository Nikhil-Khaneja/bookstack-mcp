"""Fallback node.

Triggered by the router when:
- input guardrail refused,
- retrieval returned empty / below-threshold,
- analyzer validation exhausted retries,
- analyzer self-confidence < ANALYZER_CONF_THRESHOLD.

Behavior: emit a safe, explicitly partial answer. If passages exist we
summarize the top one verbatim with its citation. If not we return a
canned "insufficient information" response. Always sets `needs_review=True`
so the UI flags the response for review (the human-review surface).
"""

from __future__ import annotations

from ..state import AgentState
from ._shared import node_timer


def fallback_node(state: AgentState) -> AgentState:
    with node_timer(state, "fallback") as ev:
        state["used_fallback"] = True
        state["needs_review"] = True
        reason = state.get("fallback_reason") or "low_confidence"
        hits = state.get("retrieved", [])

        if hits:
            top = hits[0]
            excerpt = (top.get("text") or "")[:500].strip()
            answer = (
                "Partial answer (confidence low, flagged for review):\n\n"
                f"{excerpt}\n\n[{top['chunk_id']}]"
            )
            citations = [int(top["chunk_id"])]
        else:
            answer = "I don't have enough information in my knowledge base to answer that."
            citations = []

        state["answer"] = answer
        state["citations"] = citations
        ev["decision"] = f"fallback:{reason}"
        ev["meta"] = {"n_hits": len(hits), "reason": reason}
    return state
