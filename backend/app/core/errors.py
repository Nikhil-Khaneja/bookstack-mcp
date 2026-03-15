"""Typed exceptions with deterministic HTTP mappings.

Everywhere in services/, raise one of these. The FastAPI layer converts
them to HTTPException via install_exception_handlers().
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class GuardrailViolation(AppError):
    status_code = 400
    code = "guardrail_violation"


class RetrievalEmpty(AppError):
    status_code = 404
    code = "retrieval_empty"


class ValidationRetryExceeded(AppError):
    status_code = 502
    code = "validation_retry_exceeded"


class BreakerOpen(AppError):
    status_code = 503
    code = "breaker_open"


class UpstreamTimeout(AppError):
    status_code = 504
    code = "upstream_timeout"


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
            },
        )
