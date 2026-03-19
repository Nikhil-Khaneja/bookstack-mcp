"""Selects the concrete LLM based on config.

Call `get_llm()` from service code. The pipeline never cares which
implementation it got; tests can inject a stub by patching this function.
"""

from __future__ import annotations

import threading

from ...core.config import get_settings
from ...core.logging import get_logger
from .base import ChatLLM
from .null_llm import NullLLM

_cached: ChatLLM | None = None
_lock = threading.Lock()
log = get_logger(__name__)


def _build() -> ChatLLM:
    settings = get_settings()
    if settings.llm_offline:
        log.warning("llm.offline_fallback", reason="GROQ_API_KEY not set")
        return NullLLM()
    try:
        from .groq_llm import GroqLLM  # local import to avoid cost when offline

        return GroqLLM()
    except Exception as exc:  # noqa: BLE001
        log.error("llm.groq_init_failed", error=str(exc))
        return NullLLM()


def get_llm() -> ChatLLM:
    global _cached
    if _cached is not None:
        return _cached
    with _lock:
        if _cached is None:
            _cached = _build()
        return _cached


def reset_llm_cache() -> None:
    """Test helper."""
    global _cached
    with _lock:
        _cached = None
