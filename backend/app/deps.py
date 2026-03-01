from .database import SessionLocal


# FastAPI dependency — gives each route its own DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
