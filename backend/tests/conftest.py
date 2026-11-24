import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def session_factory():
    """A fresh in-memory database for every test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def client(session_factory, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "ACCESS_CODE", "")  # gate off unless a test turns it on

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


DEFAULTS = dict(file_path="a.py", line=1, message="msg", ai_explanation=None)


@pytest.fixture()
def seed_analysis(session_factory):
    """Create an analysis plus findings; returns the analysis id."""

    def _seed(findings, status="completed"):
        db = session_factory()
        try:
            analysis = models.Analysis(repo_url="https://github.com/o/r", status=status)
            db.add(analysis)
            db.commit()
            db.refresh(analysis)
            for f in findings:
                db.add(models.Finding(analysis_id=analysis.id, **{**DEFAULTS, **f}))
            db.commit()
            return analysis.id
        finally:
            db.close()

    return _seed