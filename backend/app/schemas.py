from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
import re


# ─────────────────────────── Author Schemas ────────────────────────────

class AuthorCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100, description="Author's first name")
    last_name:  str = Field(..., min_length=1, max_length=100, description="Author's last name")
    email:      EmailStr


class AuthorUpdate(BaseModel):
    first_name: Optional[str]      = Field(None, min_length=1, max_length=100)
    last_name:  Optional[str]      = Field(None, min_length=1, max_length=100)
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
    title:            str = Field(..., min_length=1, max_length=255)
    isbn:             str = Field(..., min_length=10, max_length=20, description="ISBN-10 or ISBN-13")
    publication_year: int = Field(..., ge=1000, le=2100, description="Year the book was published")
    available_copies: int = Field(default=1, ge=0, description="Number of copies available")
    author_id:        int = Field(..., gt=0)

    @field_validator("isbn")
    @classmethod
    def isbn_must_be_numeric(cls, v):
        # Strip hyphens/spaces and check remaining chars are digits
        cleaned = re.sub(r"[\s\-]", "", v)
        if not cleaned.isdigit():
            raise ValueError("ISBN must contain only digits (hyphens and spaces allowed)")
        return v


class BookUpdate(BaseModel):
    title:            Optional[str] = Field(None, min_length=1, max_length=255)
    isbn:             Optional[str] = Field(None, min_length=10, max_length=20)
    publication_year: Optional[int] = Field(None, ge=1000, le=2100)
    available_copies: Optional[int] = Field(None, ge=0)
    author_id:        Optional[int] = Field(None, gt=0)


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
