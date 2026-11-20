import time

from sqlalchemy import select

from .database import SessionLocal
from .models import Analysis, Finding
from .analyzers.repo import clone_repo, cleanup
from .analyzers.ruff_runner import run_ruff
from .analyzers.bandit_runner import run_bandit
from .analyzers.radon_runner import run_radon
from .analyzers.pip_audit_runner import run_pip_audit
from .explainer import explain_finding

TOOLS = [
    ("ruff", run_ruff),
    ("bandit", run_bandit),
    ("radon", run_radon),
    ("pip-audit", run_pip_audit),
]

TOP_N = 10
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
CATEGORY_RANK = {"security": 0, "dependency": 1, "bug": 2}


def explain_top_findings(db, analysis_id: int) -> None:
    findings = db.scalars(
        select(Finding).where(Finding.analysis_id == analysis_id)
    ).all()
    findings.sort(
        key=lambda f: (
            SEVERITY_RANK.get(f.severity, 3),
            CATEGORY_RANK.get(f.category, 3),
        )
    )
    for f in findings[:TOP_N]:
        if f.ai_explanation:
            continue  # already explained: reuse it, no new LLM call
        try:
            f.ai_explanation = explain_finding(f)
            db.commit()
        except Exception:
            db.rollback()  # one failed explanation must not stop the rest
            continue
        time.sleep(1)  # be gentle with free-tier rate limits


def run_analysis(analysis_id: int) -> None:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        analysis.status = "running"
        db.commit()

        repo_path = clone_repo(analysis.repo_url)
        findings = []
        tool_errors = []
        try:
            for name, runner in TOOLS:
                try:
                    findings += runner(repo_path)
                except Exception as exc:
                    # one broken tool must not sink the whole analysis
                    tool_errors.append(f"{name}: {str(exc)[:200]}")
        finally:
            cleanup(repo_path)

        db.add_all(Finding(analysis_id=analysis_id, **f) for f in findings)

        if tool_errors and len(tool_errors) == len(TOOLS):
            analysis.status = "failed"
        elif tool_errors:
            analysis.status = "partial"
        else:
            analysis.status = "completed"
        analysis.error = " | ".join(tool_errors)[:1000] if tool_errors else None
        db.commit()

        # AI explanations come last, so findings are viewable before they finish
        try:
            explain_top_findings(db, analysis_id)
        except Exception:
            db.rollback()
    except Exception as exc:
        db.rollback()
        analysis = db.get(Analysis, analysis_id)
        analysis.status = "failed"
        analysis.error = str(exc)[:1000]
        db.commit()
    finally:
        db.close()