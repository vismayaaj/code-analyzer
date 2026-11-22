import json
from types import SimpleNamespace

import pytest

from app.analyzers import pip_audit_runner


def fake_run(stdout, returncode=1, stderr=""):
    def _run(*args, **kwargs):
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return _run


def write_requirements(folder):
    (folder / "requirements.txt").write_text("flask==0.12\n")


def audit_output(vulns):
    return json.dumps({"dependencies": [{"name": "flask", "version": "0.12", "vulns": vulns}]})


def test_no_requirements_file_returns_empty_list(tmp_path):
    assert pip_audit_runner.run_pip_audit(str(tmp_path)) == []


def test_vulnerability_becomes_a_finding(tmp_path, monkeypatch):
    write_requirements(tmp_path)
    vulns = [{"id": "PYSEC-1", "fix_versions": ["1.0"], "description": "Bad thing."}]
    monkeypatch.setattr(pip_audit_runner.subprocess, "run", fake_run(audit_output(vulns)))

    findings = pip_audit_runner.run_pip_audit(str(tmp_path))

    assert len(findings) == 1
    f = findings[0]
    assert f["tool"] == "pip-audit"
    assert f["category"] == "dependency"
    assert f["severity"] == "high"
    assert f["rule_id"] == "PYSEC-1"
    assert "upgrade to 1.0" in f["message"]


def test_duplicate_vulnerability_ids_are_reported_once(tmp_path, monkeypatch):
    write_requirements(tmp_path)
    vuln = {"id": "PYSEC-1", "fix_versions": ["1.0"], "description": "Bad thing."}
    monkeypatch.setattr(pip_audit_runner.subprocess, "run", fake_run(audit_output([vuln, vuln])))

    assert len(pip_audit_runner.run_pip_audit(str(tmp_path))) == 1


def test_missing_fix_version_is_mentioned(tmp_path, monkeypatch):
    write_requirements(tmp_path)
    vulns = [{"id": "PYSEC-2", "fix_versions": [], "description": "No patch yet."}]
    monkeypatch.setattr(pip_audit_runner.subprocess, "run", fake_run(audit_output(vulns)))

    findings = pip_audit_runner.run_pip_audit(str(tmp_path))

    assert "No fixed version published" in findings[0]["message"]


def test_non_json_output_raises_runtime_error(tmp_path, monkeypatch):
    write_requirements(tmp_path)
    monkeypatch.setattr(
        pip_audit_runner.subprocess, "run", fake_run("not json", returncode=2, stderr="boom")
    )

    with pytest.raises(RuntimeError, match="pip-audit failed"):
        pip_audit_runner.run_pip_audit(str(tmp_path))