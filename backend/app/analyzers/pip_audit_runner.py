import json
import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 120


def run_pip_audit(repo_path) -> list[dict]:
    req_file = Path(repo_path) / "requirements.txt"
    if not req_file.is_file():
        return []  # no requirements.txt -> nothing to audit

    result = subprocess.run(
        [
            sys.executable, "-m", "pip_audit",
            "-r", str(req_file),
            "--no-deps", "--disable-pip",
            "--format", "json",
            "--progress-spinner", "off",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT_SECONDS,
    )

    # Exit code 1 just means "vulnerabilities found", which is normal.
    # If there is no JSON at all, pip-audit really failed.
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"pip-audit failed: {result.stderr[-500:]}")

    findings = []
    seen = set()  # pip-audit can report the same vulnerability twice
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            vuln_id = vuln.get("id")
            if (dep["name"], vuln_id) in seen:
                continue
            seen.add((dep["name"], vuln_id))

            fixes = vuln.get("fix_versions") or []
            fix_text = (
                f" Fix: upgrade to {', '.join(fixes)}."
                if fixes
                else " No fixed version published."
            )
            description = (vuln.get("description") or "").strip()[:300]
            findings.append(
                {
                    "tool": "pip-audit",
                    "category": "dependency",
                    "severity": "high",  # pip-audit gives no severity; known vuln = high for v1
                    "file_path": "requirements.txt",
                    "line": None,
                    "rule_id": vuln_id,
                    "message": f"{dep['name']} {dep['version']}: {description}{fix_text}",
                }
            )
    return findings