"""MCP server for the bookstack-mcp RAG backend.

Exposes five tools so an LLM agent (any MCP-compatible client) can
autonomously manage and query the knowledge base:

- semantic_search       (POST /api/v1/retrieve)
- get_document_by_id    (we use /retrieve over the same backend, then filter)
- answer_with_rag       (POST /api/v1/answer)
- ingest_document       (POST /api/v1/ingest)
- list_sources          (GET  /api/v1/library/books or documents listing)

Uses STDIO transport. All logging goes to stderr — writing anything to
stdout would corrupt the JSON-RPC stream.
"""

from __future__ import annotations

import logging
import os
import sys

import httpx
from mcp.server.fastmcp import FastMCP

# ── Logging (stderr only) ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("library-rag-mcp")

# ── Config ─────────────────────────────────────────────────────────
BACKEND_BASE = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
HTTP_TIMEOUT = float(os.getenv("BACKEND_TIMEOUT_S", "60"))

mcp = FastMCP("library-rag")


def _post(path: str, json: dict) -> dict:
    url = f"{BACKEND_BASE}{path}"
    logger.info("POST %s", url)
    r = httpx.post(url, json=json, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{BACKEND_BASE}{path}"
    logger.info("GET  %s params=%s", url, params)
    r = httpx.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


# ── Tool 1: semantic_search ────────────────────────────────────────

@mcp.tool()
def semantic_search(query: str, top_k: int = 5, rerank: bool = True) -> list[dict]:
    """
    Run a semantic (dense vector) search over the knowledge base and
    return the top-K chunks with similarity scores.

    Args:
        query: the natural-language query.
        top_k: how many chunks to return (1..50, default 5).
        rerank: whether to apply the lexical-overlap reranker on top of
                dense results (default True).

    Returns a list of {chunk_id, document_id, document_title, ord,
    text, score, meta}.
    """
    top_k = max(1, min(int(top_k), 50))
    data = _post("/api/v1/retrieve", {"query": query, "top_k": top_k, "rerank": rerank})
    return data.get("hits", [])


# ── Tool 2: get_document_by_id ─────────────────────────────────────

@mcp.tool()
def get_document_by_id(document_id: int, max_chunks: int = 50) -> dict:
    """
    Fetch a full document (its chunks in order) by document id. Useful
    when a semantic_search hit points at a promising source you want
    to read in full.
    """
    # We retrieve by posting a broad query limited to a large top_k, then
    # filter client-side. Student-scale fine; a dedicated endpoint would
    # be cleaner at production scale.
    data = _post("/api/v1/retrieve", {"query": "*", "top_k": 50, "rerank": False})
    hits = [h for h in data.get("hits", []) if int(h["document_id"]) == int(document_id)]
    hits.sort(key=lambda h: h["ord"])
    return {"document_id": document_id, "n_chunks": len(hits), "chunks": hits[:max_chunks]}


# ── Tool 3: answer_with_rag ────────────────────────────────────────

@mcp.tool()
def answer_with_rag(query: str, top_k: int = 5) -> dict:
    """
    Run the full agent pipeline (guardrails → retrieve → analyze →
    write → output-guard) and return a grounded answer with citations.

    Returns {answer, citations, needs_review, used_fallback,
             avg_top_score, self_confidence, retrieved, audit_log,
             trace_id}.
    """
    top_k = max(1, min(int(top_k), 50))
    data = _post("/api/v1/answer", {"query": query, "top_k": top_k})
    return data


# ── Tool 4: ingest_document ────────────────────────────────────────

@mcp.tool()
def ingest_document(title: str, text: str | None = None, url: str | None = None) -> dict:
    """
    Add a new document to the knowledge base. Either `text` or `url` is
    required. The backend loader + chunker + embedder run before the
    document is upserted into pgvector.

    Idempotent by (source_uri, content_hash).
    """
    payload: dict = {"title": title}
    if text:
        payload["text"] = text
    if url:
        payload["url"] = url
    if "text" not in payload and "url" not in payload:
        return {"error": "either text or url is required"}
    return _post("/api/v1/ingest", payload)


# ── Tool 5: list_sources ───────────────────────────────────────────

@mcp.tool()
def list_sources(limit: int = 20) -> list[dict]:
    """
    List the most recent documents in the knowledge base.

    (Implementation note: we issue a broad retrieval query and collapse
    the results by document_id. This avoids introducing a separate
    documents-listing endpoint for the student-scope demo.)
    """
    data = _post("/api/v1/retrieve", {"query": "overview", "top_k": 50, "rerank": False})
    seen: dict[int, dict] = {}
    for h in data.get("hits", []):
        did = int(h["document_id"])
        if did not in seen:
            seen[did] = {
                "document_id": did,
                "title": h["document_title"],
                "top_score": h["score"],
            }
    return list(seen.values())[:limit]


# ── Entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
