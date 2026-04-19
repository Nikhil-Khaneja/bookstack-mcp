"""Central configuration. Single source of truth for every env-driven knob.

Nothing else in the codebase should read os.environ directly — go through
Settings so defaults and types stay consistent.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────
    app_name: str = "bookstack-mcp"
    app_env: str = Field(default="dev", description="dev|test|prod")

    # ── Database ────────────────────────────────────────────────────
    # Default assumes local Postgres with pgvector. docker-compose provides this.
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/bookstack",
        description="SQLAlchemy URL. Must be Postgres for RAG (pgvector).",
    )
    database_echo: bool = False

    # ── CORS ────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── LLM (Groq) ──────────────────────────────────────────────────
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_timeout_s: float = 30.0

    # ── Embeddings ──────────────────────────────────────────────────
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embed_dim: int = 384  # must match the model above

    # ── Chunking ────────────────────────────────────────────────────
    chunk_size: int = 512
    chunk_overlap: int = 64

    # ── Retrieval ───────────────────────────────────────────────────
    top_k: int = 5
    retrieval_conf_threshold: float = 0.25
    analyzer_conf_threshold: float = 0.55

    # ── Guardrails ──────────────────────────────────────────────────
    max_query_chars: int = 2000
    output_validation_max_retries: int = 2

    # ── Prompts ─────────────────────────────────────────────────────
    prompt_version: str = "v1"

    # ── Observability ───────────────────────────────────────────────
    mlflow_tracking_uri: str | None = None
    audit_log_dir: Path = Path("./audit")

    # ── Derived helpers ─────────────────────────────────────────────
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_offline(self) -> bool:
        """True when no LLM key is configured — pipeline falls back to extractive mode."""
        return not bool(self.groq_api_key)

    @property
    def mlflow_enabled(self) -> bool:
        return bool(self.mlflow_tracking_uri)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
