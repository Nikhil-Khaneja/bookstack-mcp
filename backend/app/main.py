from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import authors, books

# Auto-create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Library Management System",
    description="RESTful API for managing books and authors",
    version="1.0.0"
)

# Allow requests from the React frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(authors.router)
app.include_router(books.router)


@app.get("/")
def home():
    return {"message": "Library Management System API — visit /docs for Swagger UI"}
