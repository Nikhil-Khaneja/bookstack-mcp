"""Durable JSONL audit trail keyed by trace_id.

One file per UTC day. Safe for concurrent appends because each call opens,
writes, and closes; we rely on the OS to atomically append short records
on POSIX. This is enough for a student-scale demo — an external log
shipper can tail these later.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from ...core.config import get_settings

_lock = Lock()


def _day_path() -> Path:
    settings = get_settings()
    settings.audit_log_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    return settings.audit_log_dir / f"audit-{day}.jsonl"


def append_events(events: list[dict]) -> None:
    if not events:
        return
    path = _day_path()
    lines = [json.dumps(e, default=str, ensure_ascii=False) + "\n" for e in events]
    with _lock, path.open("a", encoding="utf-8") as f:
        f.writelines(lines)


def read_events_for_trace(trace_id: str, *, day: str | None = None) -> list[dict]:
    """Read back all events for one trace_id (mostly for the debug UI)."""
    settings = get_settings()
    if day is None:
        day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    path = settings.audit_log_dir / f"audit-{day}.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("trace_id") == trace_id:
                out.append(row)
    return out
