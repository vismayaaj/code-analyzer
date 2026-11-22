import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from app.analyzers import bandit_runner


def fake_run(stdout="", returncode=0, stderr=""):
    calls = []

    def _run(cmd, *args, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    _run.calls = calls
    return _run


def issue(path, **overrides):
    data = {
        "filename": path,
        "issue_severity": "HIGH",
        "line_number": 7,
        "test_id": "B602",
        "issue_text": "subprocess call with shell=True identified",
    }
    data.update(overrides)
    return data


def report(*issues):
    return json.dumps({"results": list(issues)})


def test_issue_fields_are_mapped_to_a_finding(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "pkg", "a.py")
    monkeypatch.setattr(bandit_runner.subprocess, "run", fake_run(report(issue(path))))

    findings = bandit_runner.run_bandit(str(tmp_path))

    assert findings == [
        {
            "tool": "bandit",
            "category": "security",
            "severity": "high",
            "file_path": "pkg/a.py",
            "line": 7,
            "rule_id": "B602",
            "message": "subprocess call with shell=True identified",
        }
    ]


@pytest.mark.parametrize(
    "bandit_value, expected",
    [("LOW", "low"), ("MEDIUM", "medium"), ("HIGH", "high"), ("SURPRISE", "low")],
)
def test_severity_mapping(tmp_path, monkeypatch, bandit_value, expected):
    path = os.path.join(str(tmp_path), "a.py")
    output = report(issue(path, issue_severity=bandit_value))
    monkeypatch.setattr(bandit_runner.subprocess, "run", fake_run(output))

    assert bandit_runner.run_bandit(str(tmp_path))[0]["severity"] == expected


def test_missing_severity_defaults_to_low(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "a.py")
    bare = {"filename": path, "line_number": 1, "test_id": "B1", "issue_text": "x"}
    monkeypatch.setattr(bandit_runner.subprocess, "run", fake_run(report(bare)))

    assert bandit_runner.run_bandit(str(tmp_path))[0]["severity"] == "low"


def test_exit_code_1_means_issues_were_found_not_a_crash(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "a.py")
    monkeypatch.setattr(
        bandit_runner.subprocess, "run", fake_run(report(issue(path)), returncode=1)
    )

    assert len(bandit_runner.run_bandit(str(tmp_path))) == 1


def test_no_results_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(bandit_runner.subprocess, "run", fake_run(report()))

    assert bandit_runner.run_bandit(str(tmp_path)) == []


def test_crash_exit_code_raises_with_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        bandit_runner.subprocess, "run", fake_run("", returncode=2, stderr="bandit exploded")
    )

    with pytest.raises(RuntimeError, match="Bandit failed: bandit exploded"):
        bandit_runner.run_bandit(str(tmp_path))


def test_empty_output_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(bandit_runner.subprocess, "run", fake_run("", returncode=0))

    with pytest.raises(RuntimeError, match="Bandit failed"):
        bandit_runner.run_bandit(str(tmp_path))


def test_timeout_raises_runtime_error(tmp_path, monkeypatch):
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="bandit", timeout=1)

    monkeypatch.setattr(bandit_runner.subprocess, "run", slow)

    with pytest.raises(RuntimeError, match="timed out"):
        bandit_runner.run_bandit(str(tmp_path))


def test_command_skips_assert_rule_and_excludes_tests_and_virtualenvs(tmp_path, monkeypatch):
    run = fake_run(report())
    monkeypatch.setattr(bandit_runner.subprocess, "run", run)

    bandit_runner.run_bandit(str(tmp_path))

    cmd = run.calls[0]
    assert cmd[cmd.index("-r") + 1] == str(tmp_path)
    assert cmd[cmd.index("-f") + 1] == "json"
    assert cmd[cmd.index("-s") + 1] == "B101"  # assert statements: noise in tests
    excludes = cmd[cmd.index("-x") + 1]
    for part in ("*/tests/*", "*/test/*", "*/venv/*", "*/.venv/*", "*/node_modules/*"):
        assert part in excludes