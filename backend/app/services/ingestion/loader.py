"""Pluggable document loaders.

V1 scope:
- inline text (primary)
- HTTP URL → text (fetched with httpx, plain-text extracted heuristically)

Wikipedia loading lives in scripts/ingest_wikipedia.py — not here — because
it is a bulk offline ingestion concern, not a request-time concern.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class DocumentDraft:
    title: str
    text: str
    source_type: str
    source_uri: str | None
    content_hash: str
    meta: dict


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    # Deliberately simple. For student scope this beats pulling in bs4 for one call.
    return _WS_RE.sub(" ", _HTML_TAG_RE.sub(" ", html)).strip()


def load_text(
    *,
    title: str,
    text: str | None = None,
    url: str | None = None,
    meta: dict | None = None,
    timeout_s: float = 10.0,
) -> DocumentDraft:
    if text is None and url is None:
        raise ValueError("loader requires either text or url")

    if text is not None:
        body = text
        source_type = "text"
        source_uri = None
    else:
        assert url is not None  # for type checker
        r = httpx.get(url, timeout=timeout_s, follow_redirects=True)
        r.raise_for_status()
        raw = r.text
        body = _strip_html(raw) if r.headers.get("content-type", "").startswith("text/html") else raw
        source_type = "url"
        source_uri = url

    body = body.strip()
    if not body:
        raise ValueError("loader produced empty document body")

    return DocumentDraft(
        title=title,
        text=body,
        source_type=source_type,
        source_uri=source_uri,
        content_hash=_content_hash(body),
        meta=meta or {},
    )
