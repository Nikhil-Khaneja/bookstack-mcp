from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base

# Auto-create tables in MySQL on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Library Management System",
    description="RESTful API for managing books and authors",
    version="1.0.0"
)

# Allow requests from the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "Library Management System API is running. Visit /docs for Swagger UI."}
