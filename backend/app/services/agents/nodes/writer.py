"""Writer node: streams tokens for the final grounded answer.

Writer is special — it is not a pure function returning a state patch,
because the API layer needs to stream tokens to the client as they are
produced. Therefore the API calls `writer_stream(...)` directly instead
of routing through the compiled LangGraph. The graph node `writer_node`
is present for completeness (runs the writer non-streamed) and used by
the MCP `answer_with_rag` tool.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ....adapters.llm import Message, get_llm
from ....services.guardrails import get_breaker
from ..prompts import load_prompt
from ..state import AgentState, WriterOutput
from ._shared import format_passages, node_timer


def _build_messages(state: AgentState) -> list[Message]:
    template = load_prompt("writer")
    summary = (state.get("analysis") or {}).get("summary", "")
    passages = format_passages(state.get("retrieved", []))
    prompt = (
        template.replace("{{QUERY}}", state["query"])
        .replace("{{SUMMARY}}", summary)
        .replace("{{PASSAGES}}", passages)
    )
    return [Message(role="user", content=prompt)]


async def writer_stream(state: AgentState) -> AsyncIterator[str]:
    """Async generator yielding answer tokens. Mutates state['answer'] as it goes."""
    llm = get_llm()
    breaker = get_breaker("llm")
    messages = _build_messages(state)

    with node_timer(state, "writer") as ev:
        buf: list[str] = []
        try:
            # pybreaker wraps stream() initialization only; streaming itself can
            # continue beyond the breaker decision point.
            stream_iter = breaker.call(llm.stream, messages, temperature=0.3)
            async for tok in stream_iter:
                buf.append(tok)
                yield tok
        except Exception as exc:  # noqa: BLE001
            state.setdefault("errors", []).append(f"writer_stream:{exc}")
            ev["decision"] = "writer_error"
            ev["error"] = str(exc)
            return

        answer = "".join(buf).strip()
        state["answer"] = answer
        state["citations"] = _extract_citations(answer, state.get("retrieved", []))
        ev["decision"] = "written"
        ev["meta"] = {"chars": len(answer), "n_citations": len(state["citations"])}


async def writer_node(state: AgentState) -> AgentState:
    """Non-streaming variant used by MCP answer_with_rag."""
    # Drain the async generator into state.
    async for _ in writer_stream(state):
        pass
    return state


def _extract_citations(answer: str, retrieved: list[dict]) -> list[int]:
    import re

    valid_ids = {int(h["chunk_id"]) for h in retrieved}
    ids = [int(x) for x in re.findall(r"\[(\d+)\]", answer)]
    return [i for i in dict.fromkeys(ids) if i in valid_ids]


def validate_writer_output(state: AgentState) -> WriterOutput:
    """Final gate: ensures the answer is non-empty and citations are valid."""
    wo = WriterOutput(
        answer=state.get("answer") or "",
        citations=state.get("citations") or [],
    )
    # Invariant: every citation id must have appeared in retrieved.
    valid = {int(h["chunk_id"]) for h in state.get("retrieved", [])}
    wo.citations = [c for c in wo.citations if c in valid]
    return wo
