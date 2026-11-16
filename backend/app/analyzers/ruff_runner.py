import json
import os
import subprocess
import sys

RUFF_TIMEOUT = 180
RULES = "E,F,W,B,SIM"  # pycodestyle, pyflakes, bugbear, simplify


def _classify(code: str) -> tuple[str, str]:
    """Map a Ruff rule code to (category, severity)."""
    if code.startswith("F8"):          # undefined names, redefinitions
        return "bug", "high"
    if code.startswith(("F", "B")):    # other pyflakes / bugbear
        return "bug", "medium"
    return "quality", "low"


def run_ruff(repo_path: str) -> list[dict]:
    cmd = [
        sys.executable, "-m", "ruff", "check", repo_path,
        "--isolated",                  # ignore the repo's own ruff config
        "--select", RULES,
        "--output-format", "json",
        "--exit-zero",                 # don't treat "issues found" as an error
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=RUFF_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Ruff timed out")

    if result.returncode != 0:
        raise RuntimeError(f"Ruff failed: {result.stderr.strip()}")

    raw = json.loads(result.stdout or "[]")
    findings = []
    for item in raw:
        code = item.get("code") or ""
        category, severity = _classify(code)
        rel_path = os.path.relpath(item["filename"], repo_path).replace("\\", "/")
        findings.append({
            "tool": "ruff",
            "category": category,
            "severity": severity,
            "file_path": rel_path,
            "line": (item.get("location") or {}).get("row"),
            "rule_id": code,
            "message": item["message"],
        })
    return findings