"""Analyzer node: LLM reads query + passages → structured AnalyzerOutput.

Uses json_mode so the LLM is constrained to emit a JSON object. The
output guardrail validates against AnalyzerOutput; on validation failure
retry_with_correction re-prompts with the validator error. After the
retry budget is exhausted, ValidationRetryExceeded bubbles up and the
router routes to `fallback_node`.
"""

from __future__ import annotations

from ....adapters.llm import Message, get_llm
from ....core.errors import ValidationRetryExceeded
from ....services.guardrails import call_with_breaker, retry_with_correction
from ..prompts import load_prompt
from ..state import AgentState, AnalyzerOutput
from ._shared import format_passages, node_timer


async def analyzer_node(state: AgentState) -> AgentState:
    llm = get_llm()
    template = load_prompt("analyzer")
    passages = format_passages(state.get("retrieved", []))
    base_prompt = template.replace("{{QUERY}}", state["query"]).replace("{{PASSAGES}}", passages)

    with node_timer(state, "analyzer") as ev:
        async def _call(correction: str | None) -> str:
            messages = [Message(role="user", content=base_prompt)]
            if correction:
                messages.append(Message(role="user", content=correction))
            return await call_with_breaker(
                "llm",
                llm.complete,
                messages,
                json_mode=True,
                temperature=0.0,
            )

        try:
            parsed: AnalyzerOutput = await retry_with_correction(
                schema=AnalyzerOutput, call=_call
            )
        except ValidationRetryExceeded as e:
            state.setdefault("errors", []).append(f"analyzer_validation:{e.message}")
            ev["decision"] = "validation_exhausted"
            ev["error"] = e.message
            # Leave analysis empty — the router will route to fallback.
            state["analysis"] = {}
            state["self_confidence"] = 0.0
            return state

        state["analysis"] = parsed.model_dump()
        state["self_confidence"] = parsed.self_confidence
        ev["confidence"] = parsed.self_confidence
        ev["decision"] = "analyzed"

    return state
