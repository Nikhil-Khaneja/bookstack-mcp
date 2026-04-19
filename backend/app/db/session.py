"""SQLAlchemy engines — both sync and async from one URL.

All CRUD uses the sync engine (unchanged from the original project).
Async is there for endpoints that shouldn't block the event loop,
specifically retrieval/ingest/ask that talk to embeddings + LLM.

Engines are lazy-initialised (first access) so unit tests that import
models but never touch a database don't need psycopg installed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from functools import lru_cache

from sqlalchemy.orm import DeclarativeBase, Session


# ── Base ─────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the app."""


# ── Lazy engine factories ─────────────────────────────────────────────────

def _ensure_psycopg_driver(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=1)
def _get_sync_engine():
    from sqlalchemy import create_engine
    from ..core.config import get_settings
    s = get_settings()
    return create_engine(s.database_url, echo=s.database_echo, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _get_async_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from ..core.config import get_settings
    s = get_settings()
    return create_async_engine(
        _ensure_psycopg_driver(s.database_url),
        echo=s.database_echo,
        pool_pre_ping=True,
        future=True,
    )


# ── Public handles (lazy) ────────────────────────────────────────────────
class _LazyEngine:
    """Proxy that creates the real engine on first attribute access."""

    def __init__(self, factory):
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_engine", None)

    def _resolve(self):
        eng = object.__getattribute__(self, "_engine")
        if eng is None:
            eng = object.__getattribute__(self, "_factory")()
            object.__setattr__(self, "_engine", eng)
        return eng

    def __getattr__(self, item):
        return getattr(self._resolve(), item)

    def __repr__(self):
        return repr(self._resolve())


engine = _LazyEngine(_get_sync_engine)
async_engine = _LazyEngine(_get_async_engine)


# ── Session factories (also lazy) ────────────────────────────────────────

@lru_cache(maxsize=1)
def _session_local():
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(
        bind=_get_sync_engine(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@lru_cache(maxsize=1)
def _async_session_local():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    return async_sessionmaker(
        bind=_get_async_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Aliases kept for backwards compatibility with code that does `from .session import SessionLocal`
class SessionLocal:  # type: ignore[no-redef]
    def __new__(cls):
        return _session_local()()


class AsyncSessionLocal:  # type: ignore[no-redef]
    def __new__(cls):
        return _async_session_local()()


def get_db() -> Iterator[Session]:
    db = _session_local()()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncIterator:
    async with _async_session_local()() as session:
        yield session
