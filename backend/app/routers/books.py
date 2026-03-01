from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import crud, schemas
from app.deps import get_db

router = APIRouter(prefix="/books", tags=["Books"])


# POST /books — create a new book
@router.post("/", response_model=schemas.BookResponse, status_code=201)
def create_book(book: schemas.BookCreate, db: Session = Depends(get_db)):
    # Make sure the author exists
    author = crud.get_author(db, author_id=book.author_id)
    if not author:
        raise HTTPException(status_code=404, detail=f"Author with id {book.author_id} not found")

    # Prevent duplicate ISBN
    existing = crud.get_book_by_isbn(db, isbn=book.isbn)
    if existing:
        raise HTTPException(status_code=400, detail="A book with this ISBN already exists")

    return crud.create_book(db=db, book=book)


# GET /books — list all books with skip/limit pagination
@router.get("/", response_model=List[schemas.BookResponse])
def read_books(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_books(db, skip=skip, limit=limit)


# GET /books/{id} — get a single book
@router.get("/{book_id}", response_model=schemas.BookResponse)
def read_book(book_id: int, db: Session = Depends(get_db)):
    book = crud.get_book(db, book_id=book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


# PUT /books/{id} — update book details
@router.put("/{book_id}", response_model=schemas.BookResponse)
def update_book(book_id: int, book: schemas.BookUpdate, db: Session = Depends(get_db)):
    db_book = crud.get_book(db, book_id=book_id)
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")

    # If changing author, verify the new author exists
    if book.author_id and book.author_id != db_book.author_id:
        if not crud.get_author(db, author_id=book.author_id):
            raise HTTPException(status_code=404, detail=f"Author with id {book.author_id} not found")

    # If changing ISBN, make sure it's not already taken
    if book.isbn and book.isbn != db_book.isbn:
        if crud.get_book_by_isbn(db, isbn=book.isbn):
            raise HTTPException(status_code=400, detail="A book with this ISBN already exists")

    return crud.update_book(db=db, book_id=book_id, book=book)


# DELETE /books/{id} — delete a book
@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    db_book = crud.get_book(db, book_id=book_id)
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    crud.delete_book(db=db, book_id=book_id)


# GET /authors/{id}/books — all books by a specific author
# (registered in authors router, but the crud function lives here in books)
