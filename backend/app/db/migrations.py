"""Lightweight bootstrap: enable pgvector, create tables, create vector index.

Not Alembic — this project is a student demo and `create_all` is acceptable.
The one thing raw `create_all` cannot do is `CREATE EXTENSION vector`, so we
run that explicitly, then create the tables, then the ivfflat index.
"""

from __future__ import annotations

from sqlalchemy import text

from .session import engine, Base


def ensure_pgvector_and_tables() -> None:
    """Idempotent. Safe to call on every startup."""
    # 1. Extension (Postgres only). On MySQL this whole function is a no-op
    #    because the RAG tables are Postgres-only by design.
    dialect = engine.dialect.name
    if dialect == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # 2. Import models so Base.metadata knows about every table before create_all.
    #    This side-effect import is intentional.
    from ..models import document as _doc_mod  # noqa: F401

    # Legacy models live on the same Base.
    from .. import models as _legacy_mod  # noqa: F401

    # 3. Tables.
    Base.metadata.create_all(bind=engine)

    # 4. Vector index (Postgres only).
    if dialect == "postgresql":
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS chunks_embedding_idx "
                    "ON chunks USING ivfflat (embedding vector_cosine_ops) "
                    "WITH (lists = 100)"
                )
            )
