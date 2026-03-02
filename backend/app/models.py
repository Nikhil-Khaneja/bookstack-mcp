from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from .database import Base


class Author(Base):
    __tablename__ = "authors"

    id           = Column(Integer, primary_key=True, index=True)
    first_name   = Column(String(100), nullable=False)
    last_name    = Column(String(100), nullable=False)
    email        = Column(String(255), unique=True, nullable=False)
    created_at   = Column(DateTime, default=func.now())
    updated_at   = Column(DateTime, default=func.now(), onupdate=func.now())

    books = relationship("Book", back_populates="author")


class Book(Base):
    __tablename__ = "books"

    id               = Column(Integer, primary_key=True, index=True)
    title            = Column(String(255), nullable=False)
    isbn             = Column(String(20), unique=True, nullable=False)
    publication_year = Column(Integer, nullable=False)
    available_copies = Column(Integer, default=1)
    author_id        = Column(Integer, ForeignKey("authors.id"), nullable=False)
    created_at       = Column(DateTime, default=func.now())
    updated_at       = Column(DateTime, default=func.now(), onupdate=func.now())

    author = relationship("Author", back_populates="books")
