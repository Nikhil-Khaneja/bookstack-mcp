from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import crud, schemas
from app.deps import get_db

router = APIRouter(prefix="/authors", tags=["Authors"])


# POST /authors — create a new author
@router.post("/", response_model=schemas.AuthorResponse, status_code=201)
def create_author(author: schemas.AuthorCreate, db: Session = Depends(get_db)):
    # Prevent duplicate emails
    existing = crud.get_author_by_email(db, email=author.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_author(db=db, author=author)


# GET /authors — list all authors with skip/limit pagination
@router.get("/", response_model=List[schemas.AuthorResponse])
def read_authors(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_authors(db, skip=skip, limit=limit)


# GET /authors/{id} — get a single author
@router.get("/{author_id}", response_model=schemas.AuthorResponse)
def read_author(author_id: int, db: Session = Depends(get_db)):
    author = crud.get_author(db, author_id=author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    return author


# PUT /authors/{id} — update author info
@router.put("/{author_id}", response_model=schemas.AuthorResponse)
def update_author(author_id: int, author: schemas.AuthorUpdate, db: Session = Depends(get_db)):
    db_author = crud.get_author(db, author_id=author_id)
    if not db_author:
        raise HTTPException(status_code=404, detail="Author not found")

    # If email is changing, make sure it's not already taken
    if author.email and author.email != db_author.email:
        if crud.get_author_by_email(db, email=author.email):
            raise HTTPException(status_code=400, detail="Email already in use by another author")

    return crud.update_author(db=db, author_id=author_id, author=author)


# DELETE /authors/{id} — delete author (blocked if they have books)
@router.delete("/{author_id}", status_code=204)
def delete_author(author_id: int, db: Session = Depends(get_db)):
    db_author = crud.get_author(db, author_id=author_id)
    if not db_author:
        raise HTTPException(status_code=404, detail="Author not found")
    if db_author.books:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete an author who has associated books. Delete their books first."
        )
    crud.delete_author(db=db, author_id=author_id)


# GET /authors/{id}/books — all books written by a specific author
@router.get("/{author_id}/books", response_model=List[schemas.BookResponse])
def get_books_by_author(author_id: int, db: Session = Depends(get_db)):
    author = crud.get_author(db, author_id=author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    return crud.get_books_by_author(db=db, author_id=author_id)
