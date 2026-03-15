"""Legacy shim. Kept so `from app.database import Base/engine/SessionLocal`
in older code paths continues to work. The canonical definitions live in
`app.db.session`.
"""

from .db.session import Base, SessionLocal, engine  # noqa: F401

__all__ = ["Base", "SessionLocal", "engine"]
