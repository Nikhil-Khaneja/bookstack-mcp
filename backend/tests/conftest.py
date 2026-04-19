"""Shared pytest fixtures for all test modules."""

from __future__ import annotations

import pytest

from app.services.retrieval.vector_store import InMemoryVectorStore
from app.services.retrieval.embedder import HashingEmbedder
from app.services.ingestion.loader import load_text
from app.services.ingestion.chunker import chunk_text


@pytest.fixture()
def hashing_embedder() -> HashingEmbedder:
    """Deterministic offline embedder — no model download needed."""
    return HashingEmbedder(dim=384)


@pytest.fixture()
def in_memory_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


@pytest.fixture()
def populated_store(in_memory_store, hashing_embedder):
    """Store pre-loaded with three documents for retrieval tests."""
    docs = [
        ("Transformers in NLP",
         "The Transformer architecture uses multi-head self-attention to process text sequences. "
         "It was introduced in the Attention Is All You Need paper. Positional encodings are added "
         "to represent token order since attention is permutation invariant."),
        ("Vector Databases",
         "Vector databases like pgvector and Pinecone store high-dimensional embeddings and "
         "support approximate nearest neighbor search for semantic retrieval. Cosine similarity "
         "is commonly used to measure distance between embedding vectors."),
        ("Python Type Hints",
         "Python type hints allow optional static typing via PEP 484. The typing module provides "
         "Protocol, TypeVar, Generic, and collection types. Pydantic uses type hints for "
         "runtime validation of data models."),
    ]
    for title, text in docs:
        draft = load_text(title=title, text=text)
        chunks = chunk_text(draft.text, size=256, overlap=32)
        vectors = hashing_embedder.encode([c.text for c in chunks])
        in_memory_store.upsert_document(draft, chunks, vectors)
    return in_memory_store
