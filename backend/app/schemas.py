from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ─────────────────────────── Author Schemas ────────────────────────────

class AuthorCreate(BaseModel):
    first_name: str
    last_name:  str
    email:      EmailStr


class AuthorUpdate(BaseModel):
    first_name: Optional[str]      = None
    last_name:  Optional[str]      = None
    email:      Optional[EmailStr] = None


class AuthorResponse(BaseModel):
    id:         int
    first_name: str
    last_name:  str
    email:      str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────── Book Schemas ──────────────────────────────

class BookCreate(BaseModel):
    title:            str
    isbn:             str
    publication_year: int
    available_copies: int = 1
    author_id:        int


class BookUpdate(BaseModel):
    title:            Optional[str] = None
    isbn:             Optional[str] = None
    publication_year: Optional[int] = None
    available_copies: Optional[int] = None
    author_id:        Optional[int] = None


class BookResponse(BaseModel):
    id:               int
    title:            str
    isbn:             str
    publication_year: int
    available_copies: int
    author_id:        int
    created_at:       datetime
    updated_at:       datetime
    author:           AuthorResponse

    class Config:
        from_attributes = True
