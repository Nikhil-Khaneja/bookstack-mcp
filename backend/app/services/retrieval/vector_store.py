"""pgvector-backed vector store.

One concrete implementation is enough. It implements:
- upsert_document(draft, chunks, vectors) → document_id, n_chunks
- search(query_vec, top_k) → list[Hit]
- get_document(id), list_documents(limit)

Cosine distance is used via pgvector's `<=>` operator. Because embeddings
come back from the embedder already normalized, `1 - distance` is a valid
cosine similarity in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...models import Chunk, Document
from ..ingestion import ChunkDraft, DocumentDraft


@dataclass(slots=True)
class VectorRow:
    text: str
    vector: list[float]
    meta: dict


@dataclass(slots=True)
class Hit:
    chunk_id: int
    document_id: int
    text: str
    score: float  # cosine similarity in [0, 1], higher = better
    document_title: str
    ord: int
    meta: dict


class PgVectorStore:
    """Session-scoped wrapper. Caller supplies the SQLAlchemy Session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── Write ────────────────────────────────────────────────────────
    def upsert_document(
        self,
        draft: DocumentDraft,
        chunks: list[ChunkDraft],
        vectors: list[list[float]],
    ) -> tuple[int, int, bool]:
        """Returns (document_id, n_chunks, created).
        created=False when the same (source_uri, content_hash) already exists.
        """
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors length mismatch")

        # Idempotency: (source_uri, content_hash) is unique. If a matching
        # document exists, return its id without re-embedding.
        existing = (
            self.session.query(Document)
            .filter(
                Document.source_uri == draft.source_uri,
                Document.content_hash == draft.content_hash,
            )
            .one_or_none()
        )
        if existing is not None:
            return existing.id, len(existing.chunks), False

        doc = Document(
            title=draft.title,
            source_type=draft.source_type,
            source_uri=draft.source_uri,
            content_hash=draft.content_hash,
            meta=draft.meta,
        )
        self.session.add(doc)
        self.session.flush()  # get doc.id

        for c, vec in zip(chunks, vectors, strict=True):
            self.session.add(
                Chunk(
                    document_id=doc.id,
                    ord=c.ord,
                    text=c.text,
                    token_count=c.token_count,
                    embedding=vec,
                    meta=c.meta,
                )
            )
        self.session.commit()
        return doc.id, len(chunks), True

    # ── Read ─────────────────────────────────────────────────────────
    def search(self, query_vec: list[float], top_k: int = 5) -> list[Hit]:
        # Parameterize the vector as a string like '[0.1,0.2,...]' which pgvector
        # parses on the cast. Pure-ORM vector comparison is clunky; raw SQL is clean.
        vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"
        stmt = text(
            """
            SELECT c.id, c.document_id, c.text, c.ord, c.meta,
                   d.title AS document_title,
                   1.0 - (c.embedding <=> CAST(:qv AS vector)) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            ORDER BY c.embedding <=> CAST(:qv AS vector) ASC
            LIMIT :k
            """
        )
        rows = self.session.execute(stmt, {"qv": vec_literal, "k": top_k}).mappings().all()
        return [
            Hit(
                chunk_id=r["id"],
                document_id=r["document_id"],
                text=r["text"],
                score=float(r["score"]),
                document_title=r["document_title"],
                ord=r["ord"],
                meta=dict(r["meta"] or {}),
            )
            for r in rows
        ]

    def get_document(self, document_id: int) -> Document | None:
        return self.session.get(Document, document_id)

    def list_documents(self, limit: int = 100) -> list[Document]:
        return (
            self.session.query(Document)
            .order_by(Document.id.desc())
            .limit(limit)
            .all()
        )

    def get_chunk(self, chunk_id: int) -> Chunk | None:
        return self.session.get(Chunk, chunk_id)


# ── In-memory fallback for tests (no Postgres required) ─────────────
class InMemoryVectorStore:
    """Tiny store used by unit tests. Not used in production paths."""

    def __init__(self) -> None:
        self._docs: dict[int, dict[str, Any]] = {}
        self._chunks: list[dict[str, Any]] = []
        self._next_doc_id = 1
        self._next_chunk_id = 1

    def upsert_document(
        self,
        draft: DocumentDraft,
        chunks: list[ChunkDraft],
        vectors: list[list[float]],
    ) -> tuple[int, int, bool]:
        for d in self._docs.values():
            if d["source_uri"] == draft.source_uri and d["content_hash"] == draft.content_hash:
                return (
                    d["id"],
                    len([c for c in self._chunks if c["document_id"] == d["id"]]),
                    False,
                )
        doc_id = self._next_doc_id
        self._next_doc_id += 1
        self._docs[doc_id] = {
            "id": doc_id,
            "title": draft.title,
            "source_uri": draft.source_uri,
            "content_hash": draft.content_hash,
            "meta": draft.meta,
        }
        for c, v in zip(chunks, vectors, strict=True):
            self._chunks.append(
                {
                    "id": self._next_chunk_id,
                    "document_id": doc_id,
                    "ord": c.ord,
                    "text": c.text,
                    "token_count": c.token_count,
                    "meta": c.meta,
                    "vector": v,
                }
            )
            self._next_chunk_id += 1
        return doc_id, len(chunks), True

    def search(self, query_vec: list[float], top_k: int = 5) -> list[Hit]:
        import numpy as np

        q = np.array(query_vec, dtype=np.float32)
        qn = q / (np.linalg.norm(q) or 1.0)
        scored = []
        for c in self._chunks:
            v = np.array(c["vector"], dtype=np.float32)
            vn = v / (np.linalg.norm(v) or 1.0)
            score = float(np.dot(qn, vn))
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits: list[Hit] = []
        for score, c in scored[:top_k]:
            doc = self._docs[c["document_id"]]
            hits.append(
                Hit(
                    chunk_id=c["id"],
                    document_id=c["document_id"],
                    text=c["text"],
                    score=max(0.0, min(1.0, score)),
                    document_title=doc["title"],
                    ord=c["ord"],
                    meta=dict(c["meta"]),
                )
            )
        return hits
