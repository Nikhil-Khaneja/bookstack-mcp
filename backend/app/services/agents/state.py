"""LangGraph shared state + per-node Pydantic output contracts.

The state is the memory of the workflow for one request. Each node
appends to `audit_log` so failures can be traced back to a specific
node (the claim "full audit trail via LangGraph shared state").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


# ── Per-node output contracts (used by the output guardrail) ─────────

class RetrieverOutput(BaseModel):
    hit_ids: list[int]
    avg_top_score: float = Field(ge=0.0, le=1.0)


class AnalyzerOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    relevance_rationale: str = Field(min_length=1, max_length=1000)
    self_confidence: float = Field(ge=0.0, le=1.0)


class WriterOutput(BaseModel):
    answer: str = Field(min_length=1)
    citations: list[int] = Field(default_factory=list)


# ── Audit event ─────────────────────────────────────────────────────

class AuditEvent(TypedDict, total=False):
    trace_id: str
    node: Literal["input_guard", "retriever", "analyzer", "writer", "fallback", "output_guard"]
    ts: str
    decision: str | None
    confidence: float | None
    error: str | None
    duration_ms: int
    meta: dict[str, Any]


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


# ── Shared state (the LangGraph "state" type) ───────────────────────

class AgentState(TypedDict, total=False):
    trace_id: str
    query: str

    # retriever fills
    retrieved: list[dict]          # list of Hit-as-dict
    avg_top_score: float

    # analyzer fills
    analysis: dict                 # AnalyzerOutput.model_dump()
    self_confidence: float

    # writer / fallback fill
    answer: str
    citations: list[int]
    needs_review: bool
    used_fallback: bool
    fallback_reason: str | None

    # cross-cutting
    audit_log: list[AuditEvent]
    errors: list[str]


def init_state(trace_id: str, query: str) -> AgentState:
    return AgentState(
        trace_id=trace_id,
        query=query,
        retrieved=[],
        avg_top_score=0.0,
        analysis={},
        self_confidence=0.0,
        answer="",
        citations=[],
        needs_review=False,
        used_fallback=False,
        fallback_reason=None,
        audit_log=[],
        errors=[],
    )
