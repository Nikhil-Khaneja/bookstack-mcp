"""Sentence-Transformers embedder with a deterministic hashing fallback.

Primary: `all-MiniLM-L6-v2` (384-dim, free, CPU-friendly). Loaded lazily on
first use so the process starts fast and tests that never hit the embedder
don't pay the model-download cost.

Fallback (HashingEmbedder): pure numpy, no model download, deterministic,
low quality. Used automatically when sentence-transformers cannot be
imported OR when the model cannot be loaded. This keeps the pipeline
runnable in minimal environments while still producing real vectors of
the right dimensionality.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Protocol, runtime_checkable

import numpy as np

from ...core.config import get_settings
from ...core.logging import get_logger

log = get_logger(__name__)


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class _SentenceTransformerEmbedder:
    def __init__(self, model_name: str, dim: int) -> None:
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model_name)
        self.name = model_name
        self.dim = dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vecs.tolist()


class HashingEmbedder:
    """Deterministic fallback. NOT production-quality, but real, unit-norm,
    and the right dimension. Used when sentence-transformers is unavailable.
    """

    def __init__(self, dim: int) -> None:
        self.name = f"hashing-{dim}"
        self.dim = dim

    def _hash_vec(self, text: str) -> np.ndarray:
        # Seed a per-text RNG from sha256 so this is deterministic but
        # spreads similar texts into nearby-ish regions via bag-of-hashes.
        v = np.zeros(self.dim, dtype=np.float32)
        tokens = [t for t in text.lower().split() if t]
        if not tokens:
            v[0] = 1.0
            return v
        for tok in tokens:
            h = int.from_bytes(hashlib.sha256(tok.encode("utf-8")).digest()[:8], "big")
            rng = np.random.default_rng(h)
            v += rng.standard_normal(self.dim).astype(np.float32)
        norm = np.linalg.norm(v)
        if norm > 0:
            v /= norm
        return v

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vec(t).tolist() for t in texts]


_cached: Embedder | None = None
_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _cached
    if _cached is not None:
        return _cached
    with _lock:
        if _cached is not None:
            return _cached
        settings = get_settings()
        try:
            _cached = _SentenceTransformerEmbedder(settings.embed_model, settings.embed_dim)
            log.info("embedder.loaded", model=settings.embed_model, dim=settings.embed_dim)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "embedder.fallback",
                reason=str(exc),
                using="hashing",
                dim=settings.embed_dim,
            )
            _cached = HashingEmbedder(settings.embed_dim)
        return _cached
