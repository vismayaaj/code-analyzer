import json
import os
import subprocess
import sys

RADON_TIMEOUT = 180
MIN_RANK = {"C", "D", "E", "F"}  # only report moderately complex or worse


def _severity(rank: str) -> str:
    if rank in ("E", "F"):
        return "high"
    if rank == "D":
        return "medium"
    return "low"


def run_radon(repo_path: str) -> list[dict]:
    cmd = [
        sys.executable, "-m", "radon", "cc", repo_path,
        "-j", "-s", "-n", "C",
        "-i", "tests,test,venv,.venv,node_modules",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=RADON_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Radon timed out")

    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"Radon failed: {result.stderr.strip()[:500]}")

    raw = json.loads(result.stdout)
    findings = []
    for filename, blocks in raw.items():
        if not isinstance(blocks, list):
            continue  # radon reports per-file errors as dicts
        rel_path = os.path.relpath(filename, repo_path).replace("\\", "/")
        for b in blocks:
            rank = b.get("rank", "C")
            if rank not in MIN_RANK:
                continue
            findings.append({
                "tool": "radon",
                "category": "complexity",
                "severity": _severity(rank),
                "file_path": rel_path,
                "line": b.get("lineno"),
                "rule_id": f"CC-{rank}",
                "message": f"{b.get('type', 'block')} '{b.get('name')}' has cyclomatic complexity {b.get('complexity')} (rank {rank})",
            })
    return findings