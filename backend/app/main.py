from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .analyzers.repo import validate_repo_url
from .database import Base, engine, get_db
from .services import run_analysis

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Code Review & Repository Analyzer")


class AnalyzeRequest(BaseModel):
    repo_url: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", status_code=202)
def analyze(req: AnalyzeRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        url = validate_repo_url(req.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    analysis = models.Analysis(repo_url=url)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    background.add_task(run_analysis, analysis.id)
    return {"id": analysis.id, "status": analysis.status}


@app.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.get(models.Analysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    total = db.scalar(
        select(func.count()).select_from(models.Finding).where(models.Finding.analysis_id == analysis_id)
    )
    findings = db.scalars(
        select(models.Finding).where(models.Finding.analysis_id == analysis_id).limit(200)
    ).all()

    return {
        "id": analysis.id,
        "repo_url": analysis.repo_url,
        "status": analysis.status,
        "error": analysis.error,
        "total_findings": total,
        "findings": [
            {
                "tool": f.tool, "category": f.category, "severity": f.severity,
                "file_path": f.file_path, "line": f.line,
                "rule_id": f.rule_id, "message": f.message,
            }
            for f in findings
        ],
    }