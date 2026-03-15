"""ORM models.

Legacy (Author, Book) come from legacy.py so existing routers/crud keep
working unchanged. New (Document, Chunk) come from document.py.
"""

from .legacy import Author, Book
from .document import Chunk, Document

__all__ = ["Author", "Book", "Document", "Chunk"]
