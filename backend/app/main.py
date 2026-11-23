from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import models
from .analyzers.repo import validate_repo_url
from .database import Base, engine, get_db
from .services import run_analysis

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Code Review & Repository Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _count_by(db: Session, column, analysis_id: int) -> dict:
    return dict(
        db.execute(
            select(column, func.count())
            .where(models.Finding.analysis_id == analysis_id)
            .group_by(column)
        ).all()
    )


@app.get("/analysis/{analysis_id}")
def get_analysis(
    analysis_id: int,
    tool: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    analysis = db.get(models.Analysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    conditions = [models.Finding.analysis_id == analysis_id]
    if tool:
        conditions.append(models.Finding.tool == tool)
    if category:
        conditions.append(models.Finding.category == category)

    severity_order = case(
        (models.Finding.severity == "high", 0),
        (models.Finding.severity == "medium", 1),
        else_=2,
    )

    total = db.scalar(select(func.count()).select_from(models.Finding).where(*conditions))
    findings = db.scalars(
        select(models.Finding)
        .where(*conditions)
        .order_by(severity_order, models.Finding.id)
        .limit(200)
    ).all()

    return {
        "id": analysis.id,
        "repo_url": analysis.repo_url,
        "status": analysis.status,
        "error": analysis.error,
        "total_findings": total,
        "findings_by_tool": _count_by(db, models.Finding.tool, analysis_id),
        "findings_by_severity": _count_by(db, models.Finding.severity, analysis_id),
        "findings_by_category": _count_by(db, models.Finding.category, analysis_id),
        "findings": [
            {
                "id": f.id,
                "tool": f.tool, "category": f.category, "severity": f.severity,
                "file_path": f.file_path, "line": f.line,
                "rule_id": f.rule_id, "message": f.message,
                "ai_explanation": f.ai_explanation,
            }
            for f in findings
        ],
    }