"""Unit tests for the lexical reranker and InMemoryVectorStore."""

from __future__ import annotations

import pytest

from app.services.retrieval.retriever import lexical_rerank
from app.services.retrieval.vector_store import Hit, InMemoryVectorStore


def _make_hit(chunk_id: int, doc_id: int, text: str, score: float, title: str = "Doc") -> Hit:
    return Hit(
        chunk_id=chunk_id,
        document_id=doc_id,
        text=text,
        score=score,
        document_title=title,
        ord=0,
        meta={},
    )


class TestLexicalRerank:
    def test_rerank_promotes_lexically_matching_hit(self):
        query = "transformer attention mechanism"
        hits = [
            _make_hit(1, 1, "The cat sat on the mat.", 0.9, "Cats"),
            _make_hit(2, 2, "Transformers use multi-head attention mechanism.", 0.7, "Transformers"),
        ]
        reranked = lexical_rerank(query, hits, weight=0.25)
        # Semantically lower-scored but lexically matching hit should rise
        top_title = reranked[0].document_title
        assert top_title == "Transformers"

    def test_rerank_preserves_all_hits(self):
        query = "test query"
        hits = [_make_hit(i, i, f"chunk {i}", 0.5) for i in range(5)]
        reranked = lexical_rerank(query, hits)
        assert len(reranked) == 5

    def test_blended_scores_are_in_range(self):
        query = "machine learning neural network"
        hits = [
            _make_hit(1, 1, "Neural networks are used in machine learning.", 0.8),
            _make_hit(2, 2, "Cooking recipes for chocolate cake.", 0.6),
        ]
        reranked = lexical_rerank(query, hits)
        for h in reranked:
            assert 0.0 <= h.score <= 1.0

    def test_empty_hits_returns_empty(self):
        result = lexical_rerank("query", [])
        assert result == []

    def test_dense_scores_stored_in_meta(self):
        query = "test"
        hits = [_make_hit(1, 1, "test document", 0.75)]
        reranked = lexical_rerank(query, hits)
        assert "dense_score" in reranked[0].meta
        assert reranked[0].meta["dense_score"] == pytest.approx(0.75)


class TestInMemoryVectorStore:
    def test_upsert_and_search(self, populated_store, hashing_embedder):
        query = "attention mechanism in transformers"
        qvec = hashing_embedder.encode([query])[0]
        hits = populated_store.search(qvec, top_k=3)
        assert len(hits) <= 3
        assert all(isinstance(h, Hit) for h in hits)

    def test_scores_sorted_descending(self, populated_store, hashing_embedder):
        qvec = hashing_embedder.encode(["vector database embedding search"])[0]
        hits = populated_store.search(qvec, top_k=5)
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)

    def test_upsert_idempotent(self, in_memory_store, hashing_embedder):
        from app.services.ingestion.loader import load_text
        from app.services.ingestion.chunker import chunk_text

        draft = load_text(title="Idempotent Doc", text="Same content every time.")
        chunks = chunk_text(draft.text)
        vecs = hashing_embedder.encode([c.text for c in chunks])

        _, n1, created1 = in_memory_store.upsert_document(draft, chunks, vecs)
        _, n2, created2 = in_memory_store.upsert_document(draft, chunks, vecs)

        assert created1 is True
        assert created2 is False
        assert n1 == n2

    def test_top_k_limits_results(self, populated_store, hashing_embedder):
        qvec = hashing_embedder.encode(["any query"])[0]
        for k in [1, 2, 3]:
            hits = populated_store.search(qvec, top_k=k)
            assert len(hits) <= k
