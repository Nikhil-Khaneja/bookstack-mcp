"""POST /api/v1/retrieve

Debug / inspection endpoint. Exposes the dense top-k retriever directly
so the frontend (and eval scripts) can see what the agent would see
before any LLM call happens.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...services.retrieval import retrieve as do_retrieve

router = APIRouter(tags=["Retrieve"])


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = True


class HitSchema(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    ord: int
    text: str
    score: float
    meta: dict


class RetrieveResponse(BaseModel):
    hits: list[HitSchema]
    avg_top_score: float


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve_endpoint(
    req: RetrieveRequest, db: Session = Depends(get_db)
) -> RetrieveResponse:
    result = do_retrieve(db, req.query, top_k=req.top_k, rerank=req.rerank)
    return RetrieveResponse(
        hits=[
            HitSchema(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_title=h.document_title,
                ord=h.ord,
                text=h.text,
                score=h.score,
                meta=h.meta,
            )
            for h in result.hits
        ],
        avg_top_score=result.avg_top_score,
    )
