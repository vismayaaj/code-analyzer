from .database import SessionLocal
from .models import Analysis, Finding
from .analyzers.repo import clone_repo, cleanup
from .analyzers.ruff_runner import run_ruff
from .analyzers.bandit_runner import run_bandit


def run_analysis(analysis_id: int) -> None:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        analysis.status = "running"
        db.commit()

        repo_path = clone_repo(analysis.repo_url)
        try:
            findings = run_ruff(repo_path) + run_bandit(repo_path)
        finally:
            cleanup(repo_path)

        db.add_all(Finding(analysis_id=analysis_id, **f) for f in findings)
        analysis.status = "completed"
        db.commit()
    except Exception as exc:
        db.rollback()
        analysis = db.get(Analysis, analysis_id)
        analysis.status = "failed"
        analysis.error = str(exc)[:1000]
        db.commit()
    finally:
        db.close()