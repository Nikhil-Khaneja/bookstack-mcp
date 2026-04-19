"""Liveness + config snapshot.

/health is a DB-reachability check; /config returns a scrubbed view of the
non-secret settings so the frontend can render them on the AI console.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ...core.config import get_settings
from ...db.session import engine

router = APIRouter(tags=["Health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "unreachable",
        "llm_offline": settings.llm_offline,
    }


@router.get("/config")
def config() -> dict:
    s = get_settings()
    return {
        "app_env": s.app_env,
        "groq_model": s.groq_model if not s.llm_offline else "offline-extractive",
        "embed_model": s.embed_model,
        "embed_dim": s.embed_dim,
        "chunk_size": s.chunk_size,
        "chunk_overlap": s.chunk_overlap,
        "top_k": s.top_k,
        "retrieval_conf_threshold": s.retrieval_conf_threshold,
        "analyzer_conf_threshold": s.analyzer_conf_threshold,
        "output_validation_max_retries": s.output_validation_max_retries,
        "prompt_version": s.prompt_version,
        "mlflow_enabled": s.mlflow_enabled,
    }
