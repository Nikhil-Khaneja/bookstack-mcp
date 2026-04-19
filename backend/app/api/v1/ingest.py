"""POST /api/v1/ingest

Accepts either inline text or a URL. Runs loader → chunker → embedder →
pgvector upsert. Idempotent by (source_uri, content_hash).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from ...core.logging import get_logger
from ...db.session import get_db
from ...services.ingestion import chunk_text, load_text
from ...services.retrieval import PgVectorStore, get_embedder

router = APIRouter(tags=["Ingest"])
log = get_logger(__name__)


class IngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    text: str | None = None
    url: HttpUrl | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    document_id: int
    n_chunks: int
    deduped: bool


@router.post("/ingest", response_model=IngestResponse, status_code=201)
def ingest(req: IngestRequest, db: Session = Depends(get_db)) -> IngestResponse:
    if req.text is None and req.url is None:
        raise HTTPException(status_code=400, detail="either text or url is required")

    try:
        draft = load_text(
            title=req.title,
            text=req.text,
            url=str(req.url) if req.url else None,
            meta=req.meta,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"loader failed: {e}") from e

    chunks = chunk_text(draft.text)
    if not chunks:
        raise HTTPException(status_code=400, detail="document produced zero chunks")

    emb = get_embedder()
    vectors = emb.encode([c.text for c in chunks])

    store = PgVectorStore(db)
    doc_id, n, created = store.upsert_document(draft, chunks, vectors)

    log.info(
        "ingest.done",
        document_id=doc_id,
        n_chunks=n,
        deduped=not created,
        title=draft.title,
    )
    return IngestResponse(document_id=doc_id, n_chunks=n, deduped=not created)
