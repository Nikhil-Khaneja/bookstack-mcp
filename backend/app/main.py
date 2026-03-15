"""FastAPI app factory.

Wires: config → logging → exception handlers → migrations → CORS → routers.
Legacy /authors and /books mounts stay so the existing React pages keep
working unchanged. New surface lives under /api/v1/*.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.v1 import router as api_v1_router
from .core.config import get_settings
from .core.errors import install_exception_handlers
from .core.logging import configure_logging, get_logger
from .db.migrations import ensure_pgvector_and_tables
from .routers import authors, books

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    log.info("app.startup", env=settings.app_env, llm_offline=settings.llm_offline)
    try:
        ensure_pgvector_and_tables()
    except Exception as exc:  # noqa: BLE001
        # Don't crash the app on DB init failure — /health will report degraded.
        log.error("db.init_failed", error=str(exc))
    yield
    log.info("app.shutdown")


app = FastAPI(title="bookstack-mcp", version="0.2.0", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_exception_handlers(app)

# New versioned API.
app.include_router(api_v1_router)

# Legacy mounts — unchanged, kept so the current React UI still works.
app.include_router(authors.router)
app.include_router(books.router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        field = " → ".join(str(e) for e in error["loc"])
        errors.append({"field": field, "message": error["msg"]})
    return JSONResponse(
        status_code=422, content={"detail": "Validation error", "errors": errors}
    )


@app.get("/")
def home():
    return {"message": "bookstack-mcp", "docs": "/docs", "v1": "/api/v1/health"}
