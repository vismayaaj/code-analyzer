import json
import os
import subprocess
import sys

BANDIT_TIMEOUT = 180

SEVERITY_MAP = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"}


def run_bandit(repo_path: str) -> list[dict]:
    cmd = [
        sys.executable, "-m", "bandit",
        "-r", repo_path,
        "-f", "json",
        "-q",
        "-s", "B101",
        "-x", "*/tests/*,*/test/*,*/.venv/*,*/venv/*,*/node_modules/*",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=BANDIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Bandit timed out")

    # Bandit exits with 1 when it finds issues, so only treat >1 as a crash
    if result.returncode > 1 or not result.stdout.strip():
        raise RuntimeError(f"Bandit failed: {result.stderr.strip()[:500]}")

    raw = json.loads(result.stdout)
    findings = []
    for item in raw.get("results", []):
        rel_path = os.path.relpath(item["filename"], repo_path).replace("\\", "/")
        findings.append({
            "tool": "bandit",
            "category": "security",
            "severity": SEVERITY_MAP.get(item.get("issue_severity", "LOW"), "low"),
            "file_path": rel_path,
            "line": item.get("line_number"),
            "rule_id": item.get("test_id"),
            "message": item.get("issue_text", ""),
        })
    return findings