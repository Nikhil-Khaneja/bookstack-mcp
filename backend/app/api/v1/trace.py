"""GET /api/v1/trace/{trace_id} — read the audit trail for one request."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...services.events import read_events_for_trace

router = APIRouter(tags=["Trace"])


@router.get("/trace/{trace_id}")
def get_trace(trace_id: str, day: str | None = Query(default=None)) -> dict:
    events = read_events_for_trace(trace_id, day=day)
    return {"trace_id": trace_id, "n_events": len(events), "events": events}
