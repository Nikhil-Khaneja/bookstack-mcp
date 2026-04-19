"""API v1 package. Each module here exposes a single APIRouter.

Mount them in main.py under prefix="/api/v1".
"""

from fastapi import APIRouter

from . import ask, health, ingest, library, retrieve, trace

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(ingest.router)
router.include_router(retrieve.router)
router.include_router(ask.router)
router.include_router(trace.router)
router.include_router(library.router)
