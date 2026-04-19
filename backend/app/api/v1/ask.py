"""POST /api/v1/ask  —  Streaming Server-Sent Events.

Runs the LangGraph agent pipeline and emits one SSE event per
interesting pipeline moment:

    event: open         — {trace_id, ts}
    event: node_start   — {node}
    event: node_end     — {node, decision, confidence, ms, error?}
    event: token        — {text}
    event: trace        — {audit_log: [...]}
    event: done         — {citations, needs_review, used_fallback, error?}
    event: error        — {code, message}   (terminal failure)

The frontend consumes this with EventSource and renders answer tokens
live while also showing the per-node trace.

A companion POST /api/v1/answer returns the final state in one JSON
response — used by MCP `answer_with_rag` and tests where streaming is
inconvenient.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...core.logging import get_logger, set_trace_id
from ...db.session import get_db
from ...services.agents import run_agent_stream

router = APIRouter(tags=["Ask"])
log = get_logger(__name__)


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)


@router.post("/ask")
async def ask(req: AskRequest, request: Request, db: Session = Depends(get_db)):
    trace_id = uuid.uuid4().hex
    set_trace_id(trace_id)
    log.info("ask.start", query_len=len(req.query), top_k=req.top_k)

    async def _event_source():
        try:
            async for ev in run_agent_stream(
                db, req.query, top_k=req.top_k, trace_id=trace_id
            ):
                if await request.is_disconnected():
                    log.warning("ask.client_disconnected", trace_id=trace_id)
                    break
                kind = ev.pop("kind")
                yield {"event": kind, "data": json.dumps(ev, default=str)}
        except Exception as exc:  # noqa: BLE001
            log.exception("ask.stream_failed")
            yield {
                "event": "error",
                "data": json.dumps({"code": "stream_failed", "message": str(exc)}),
            }

    return EventSourceResponse(_event_source(), ping=15)


# ── Non-streaming companion for MCP and tests ───────────────────────

class AnswerResponse(BaseModel):
    trace_id: str
    answer: str
    citations: list[int]
    needs_review: bool
    used_fallback: bool
    avg_top_score: float
    self_confidence: float
    retrieved: list[dict]
    audit_log: list[dict]
    error: str | None = None


@router.post("/answer", response_model=AnswerResponse)
async def answer(req: AskRequest, db: Session = Depends(get_db)) -> AnswerResponse:
    trace_id = uuid.uuid4().hex
    set_trace_id(trace_id)

    final: dict = {}
    audit: list[dict] = []
    tokens: list[str] = []
    retrieved: list[dict] = []
    async for ev in run_agent_stream(db, req.query, top_k=req.top_k, trace_id=trace_id):
        kind = ev.get("kind")
        if kind == "token":
            tokens.append(ev.get("text", ""))
        elif kind == "hits":
            retrieved = ev.get("retrieved", [])
        elif kind == "trace":
            audit = ev.get("audit_log", [])
        elif kind == "done":
            final = ev

    answer_text = "".join(tokens).strip()
    return AnswerResponse(
        trace_id=final.get("trace_id") or trace_id,
        answer=answer_text,
        citations=final.get("citations", []),
        needs_review=final.get("needs_review", False),
        used_fallback=final.get("used_fallback", False),
        avg_top_score=_find_score(audit, "retriever"),
        self_confidence=_find_score(audit, "analyzer"),
        retrieved=retrieved,
        audit_log=audit,
        error=final.get("error"),
    )


def _find_score(audit: list[dict], node: str) -> float:
    for e in audit:
        if e.get("node") == node and e.get("confidence") is not None:
            try:
                return float(e["confidence"])
            except (TypeError, ValueError):
                pass
    return 0.0
