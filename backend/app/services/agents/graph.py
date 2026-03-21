"""LangGraph state machine wiring.

Nodes: input_guard → retriever → analyzer → writer → output_guard → END
                                  │           │
                                  └──────────▶ fallback ──▶ output_guard

The graph itself is used for the NON-streaming path (MCP `answer_with_rag`
and tests). The streaming /ask endpoint runs an equivalent path manually
in a generator so tokens can be forwarded to SSE as they arrive. Both
paths share the same nodes and therefore identical routing + audit
semantics.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.errors import AppError, GuardrailViolation
from ...core.logging import get_logger
from ...services.guardrails import validate_input
from ..events.audit import append_events
from .nodes import analyzer_node, fallback_node, retriever_node_factory, writer_stream
from .nodes.writer import validate_writer_output, writer_node
from .nodes._shared import node_timer
from .state import AgentState, init_state, now_iso

log = get_logger(__name__)


# ── Node factories that close over request-scoped deps ─────────────

def _input_guard_node():
    def _node(state: AgentState) -> AgentState:
        with node_timer(state, "input_guard") as ev:
            try:
                validate_input(state["query"])
                ev["decision"] = "input_ok"
            except GuardrailViolation as e:
                state["fallback_reason"] = f"input_guardrail:{e.message}"
                state.setdefault("errors", []).append(f"input_guard:{e.message}")
                ev["decision"] = "input_rejected"
                ev["error"] = e.message
        return state

    return _node


def _output_guard_node():
    def _node(state: AgentState) -> AgentState:
        with node_timer(state, "output_guard") as ev:
            wo = validate_writer_output(state)
            state["answer"] = wo.answer
            state["citations"] = wo.citations
            ev["decision"] = "output_ok"
            ev["meta"] = {"n_citations": len(wo.citations)}
        return state

    return _node


# ── Router predicates ──────────────────────────────────────────────

def _after_input_guard(state: AgentState) -> str:
    if state.get("fallback_reason"):
        return "fallback"
    return "retriever"


def _after_retriever(state: AgentState) -> str:
    s = get_settings()
    if not state.get("retrieved"):
        state["fallback_reason"] = "retrieval_empty"
        return "fallback"
    if state.get("avg_top_score", 0.0) < s.retrieval_conf_threshold:
        state["fallback_reason"] = "retrieval_below_threshold"
        return "fallback"
    return "analyzer"


def _after_analyzer(state: AgentState) -> str:
    s = get_settings()
    if not state.get("analysis"):
        state["fallback_reason"] = "analyzer_validation_failed"
        return "fallback"
    if state.get("self_confidence", 0.0) < s.analyzer_conf_threshold:
        state["fallback_reason"] = "analyzer_low_confidence"
        return "fallback"
    return "writer"


# ── Graph builder ──────────────────────────────────────────────────

def build_graph(session: Session, *, top_k: int):
    """Compile the LangGraph. The writer node here is the NON-streaming
    variant; use `run_agent_stream` for SSE-backed token streaming.
    """
    g = StateGraph(AgentState)
    g.add_node("input_guard", _input_guard_node())
    g.add_node("retriever", retriever_node_factory(session, top_k))
    g.add_node("analyzer", analyzer_node)
    g.add_node("writer", writer_node)
    g.add_node("fallback", fallback_node)
    g.add_node("output_guard", _output_guard_node())

    g.set_entry_point("input_guard")
    g.add_conditional_edges(
        "input_guard",
        _after_input_guard,
        {"retriever": "retriever", "fallback": "fallback"},
    )
    g.add_conditional_edges(
        "retriever",
        _after_retriever,
        {"analyzer": "analyzer", "fallback": "fallback"},
    )
    g.add_conditional_edges(
        "analyzer",
        _after_analyzer,
        {"writer": "writer", "fallback": "fallback"},
    )
    g.add_edge("writer", "output_guard")
    g.add_edge("fallback", "output_guard")
    g.add_edge("output_guard", END)

    return g.compile()


# ── Streaming runner (used by POST /api/v1/ask) ────────────────────

async def run_agent_stream(
    session: Session,
    query: str,
    *,
    top_k: int | None = None,
    trace_id: str | None = None,
) -> AsyncIterator[dict]:
    """Runs the same logical pipeline as build_graph, but yields events:

        {"kind": "open", ...}
        {"kind": "node_start", "node": "..."}
        {"kind": "node_end",   "node": "...", "decision": "...", "ms": ...}
        {"kind": "token",      "text": "..."}
        {"kind": "trace",      "audit_log": [...]}
        {"kind": "done",       "citations": [...], "needs_review": bool, "error": str|None}
    """
    s = get_settings()
    k = top_k or s.top_k
    tid = trace_id or uuid.uuid4().hex
    state = init_state(tid, query)

    yield {"kind": "open", "trace_id": tid, "ts": now_iso()}

    try:
        # ── input guard ────────────────────────────────────────────
        yield {"kind": "node_start", "node": "input_guard"}
        _input_guard_node()(state)
        yield _emit_last_event(state, "input_guard")
        if state.get("fallback_reason"):
            async for ev in _do_fallback_and_emit(state):
                yield ev
            async for ev in _finalize(state):
                yield ev
            return

        # ── retriever ──────────────────────────────────────────────
        yield {"kind": "node_start", "node": "retriever"}
        retriever_node_factory(session, k)(state)
        yield _emit_last_event(state, "retriever")
        yield {"kind": "hits", "retrieved": state.get("retrieved", [])}
        decision = _after_retriever(state)
        if decision == "fallback":
            async for ev in _do_fallback_and_emit(state):
                yield ev
            async for ev in _finalize(state):
                yield ev
            return

        # ── analyzer ───────────────────────────────────────────────
        yield {"kind": "node_start", "node": "analyzer"}
        await analyzer_node(state)
        yield _emit_last_event(state, "analyzer")
        decision = _after_analyzer(state)
        if decision == "fallback":
            async for ev in _do_fallback_and_emit(state):
                yield ev
            async for ev in _finalize(state):
                yield ev
            return

        # ── writer (streaming) ─────────────────────────────────────
        yield {"kind": "node_start", "node": "writer"}
        async for tok in writer_stream(state):
            yield {"kind": "token", "text": tok}
        yield _emit_last_event(state, "writer")

        async for ev in _finalize(state):
            yield ev

    except AppError as e:
        log.error("agent.error", code=e.code, message=e.message)
        state.setdefault("errors", []).append(f"{e.code}:{e.message}")
        state["fallback_reason"] = f"upstream:{e.code}"
        async for ev in _do_fallback_and_emit(state):
            yield ev
        async for ev in _finalize(state):
            yield ev
    except Exception as e:  # noqa: BLE001
        log.exception("agent.unhandled")
        state.setdefault("errors", []).append(f"unhandled:{e}")
        state["fallback_reason"] = "unhandled"
        async for ev in _do_fallback_and_emit(state):
            yield ev
        async for ev in _finalize(state, error=str(e)):
            yield ev


# ── helpers for the streaming runner ───────────────────────────────

def _emit_last_event(state: AgentState, node: str) -> dict:
    """Find the just-appended audit event and project it to an SSE node_end."""
    log_tail = state.get("audit_log", [])
    ev = log_tail[-1] if log_tail else {}
    return {
        "kind": "node_end",
        "node": node,
        "decision": ev.get("decision"),
        "confidence": ev.get("confidence"),
        "ms": ev.get("duration_ms"),
        "error": ev.get("error"),
    }


async def _do_fallback_and_emit(state: AgentState) -> AsyncIterator[dict]:
    yield {"kind": "node_start", "node": "fallback"}
    fallback_node(state)
    yield _emit_last_event(state, "fallback")
    # The fallback answer isn't streamed token-by-token (it's short and
    # deterministic) — forward it as a single chunk so the UI has content.
    if state.get("answer"):
        yield {"kind": "token", "text": state["answer"]}


async def _finalize(state: AgentState, *, error: str | None = None) -> AsyncIterator[dict]:
    yield {"kind": "node_start", "node": "output_guard"}
    _output_guard_node()(state)
    yield _emit_last_event(state, "output_guard")

    # Persist audit trail and push a trace frame before done.
    try:
        append_events(state.get("audit_log", []))
    except Exception as e:  # noqa: BLE001
        log.warning("audit.append_failed", error=str(e))

    yield {"kind": "trace", "audit_log": state.get("audit_log", [])}
    yield {
        "kind": "done",
        "trace_id": state.get("trace_id"),
        "citations": state.get("citations", []),
        "needs_review": state.get("needs_review", False),
        "used_fallback": state.get("used_fallback", False),
        "error": error,
    }
