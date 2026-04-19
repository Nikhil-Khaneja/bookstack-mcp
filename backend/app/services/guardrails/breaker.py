"""Exponential backoff (tenacity) + circuit breaker (pybreaker).

Wrap every external network call in `call_with_breaker` so flaky upstreams
fail fast instead of hanging the request. Each named breaker is shared
process-wide — so a downed Groq endpoint trips once and short-circuits all
concurrent requests until the reset timeout elapses.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import TypeVar

import pybreaker
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ...core.errors import BreakerOpen, UpstreamTimeout
from ...core.logging import get_logger

T = TypeVar("T")
log = get_logger(__name__)

_BREAKERS: dict[str, pybreaker.CircuitBreaker] = {}


def get_breaker(name: str) -> pybreaker.CircuitBreaker:
    """Lazy singleton breaker per logical upstream (llm, http, embeddings, ...)."""
    br = _BREAKERS.get(name)
    if br is None:
        br = pybreaker.CircuitBreaker(
            fail_max=5,
            reset_timeout=30,
            name=name,
        )
        _BREAKERS[name] = br
    return br


async def call_with_breaker(
    name: str,
    fn: Callable[..., Awaitable[T] | T],
    *args,
    max_attempts: int = 4,
    **kwargs,
) -> T:
    """Run `fn(*args, **kwargs)` through a tenacity retry + circuit breaker.

    Works for both sync and async `fn`. Translates breaker/retry failures
    into typed AppError subclasses so the API layer maps them to HTTP.
    """
    breaker = get_breaker(name)

    async def _once() -> T:
        try:
            result = breaker.call(fn, *args, **kwargs)
        except pybreaker.CircuitBreakerError as e:
            raise BreakerOpen(f"circuit '{name}' is open") from e
        if inspect.isawaitable(result):
            return await result
        return result

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError, OSError)),
            reraise=True,
        ):
            with attempt:
                return await _once()
    except RetryError as e:  # pragma: no cover
        raise UpstreamTimeout(f"upstream '{name}' failed after retries") from e
    except (asyncio.TimeoutError, ConnectionError, OSError) as e:
        raise UpstreamTimeout(f"upstream '{name}' timeout: {e}") from e
    # Unreachable
    raise UpstreamTimeout(f"upstream '{name}' unknown failure")
