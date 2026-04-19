"""Top-level retrieve() function composed by embedder + vector store.

Also contains a simple lexical reranker used as a fallback when a
cross-encoder isn't installed. It rewards overlap of query terms in
the chunk text, blended with the dense score.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ...core.config import get_settings
from .embedder import get_embedder
from .vector_store import Hit, PgVectorStore


@dataclass(slots=True)
class RetrieveResult:
    hits: list[Hit]
    avg_top_score: float


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(s: str) -> list[str]:
    return _TOKEN_RE.findall(s.lower())


def lexical_rerank(query: str, hits: list[Hit], weight: float = 0.25) -> list[Hit]:
    """Blend dense similarity with a cheap lexical overlap signal.

    score' = (1 - w) * dense_score + w * lexical_score
    where lexical_score = (|q ∩ c| / |q|) clipped to [0, 1].
    """
    q_tokens = Counter(_tokenize(query))
    q_total = sum(q_tokens.values()) or 1
    reranked: list[Hit] = []
    for h in hits:
        c_tokens = Counter(_tokenize(h.text))
        overlap = sum((q_tokens & c_tokens).values())
        lex = min(1.0, overlap / q_total)
        blended = (1.0 - weight) * h.score + weight * lex
        reranked.append(
            Hit(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                text=h.text,
                score=max(0.0, min(1.0, blended)),
                document_title=h.document_title,
                ord=h.ord,
                meta={**h.meta, "dense_score": h.score, "lex_score": lex},
            )
        )
    reranked.sort(key=lambda h: h.score, reverse=True)
    return reranked


def retrieve(
    session: Session,
    query: str,
    *,
    top_k: int | None = None,
    rerank: bool = True,
) -> RetrieveResult:
    settings = get_settings()
    k = top_k or settings.top_k
    if k < 1:
        raise ValueError("top_k must be >= 1")

    emb = get_embedder()
    query_vec = emb.encode([query])[0]

    store = PgVectorStore(session)
    # Over-fetch then rerank to k, so the blended ordering has room to improve.
    over_k = min(max(k * 3, k), 50)
    raw_hits = store.search(query_vec, top_k=over_k)

    hits = lexical_rerank(query, raw_hits) if rerank else raw_hits
    hits = hits[:k]

    avg = sum(h.score for h in hits) / len(hits) if hits else 0.0
    return RetrieveResult(hits=hits, avg_top_score=avg)
