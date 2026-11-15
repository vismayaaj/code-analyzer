from fastapi import FastAPI
from .database import Base, engine
from . import model

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Code Review & Repository Analyzer")

@app.get("/health")
def health():
    return {"status": "ok"}