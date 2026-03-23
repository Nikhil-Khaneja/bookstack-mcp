"""Legacy CRUD rehomed under /api/v1/library/*.

Re-uses the existing authors + books routers verbatim; only the mount
prefix changes. The old paths (/authors, /books) remain for backward
compatibility with the existing frontend until it is migrated.
"""

from fastapi import APIRouter

from ...routers import authors, books

router = APIRouter(prefix="/library")

# Mount the existing routers. Their own prefixes ("/authors", "/books") are preserved.
router.include_router(authors.router)
router.include_router(books.router)
