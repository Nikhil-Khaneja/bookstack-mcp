"""Document + Chunk models for the RAG corpus.

One Document represents one source (Wikipedia article, seed text file, etc).
It is split into many Chunks. Each Chunk carries a 384-dim embedding that
pgvector indexes with cosine distance.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from pgvector.sqlalchemy import Vector

from ..core.config import get_settings
from ..db.session import Base

_DIM = get_settings().embed_dim


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(32), nullable=False, default="text")  # text|url|wikipedia
    source_uri = Column(String(1024), nullable=True, index=True)
    title = Column(String(512), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    chunks = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source_uri", "content_hash", name="uq_source_hash"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    ord = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    embedding = Column(Vector(_DIM), nullable=False)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=func.now())

    document = relationship("Document", back_populates="chunks")
