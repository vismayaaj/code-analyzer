import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from app.analyzers import ruff_runner


def fake_run(stdout="", returncode=0, stderr=""):
    calls = []

    def _run(cmd, *args, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    _run.calls = calls
    return _run


def item(path, **overrides):
    data = {
        "filename": path,
        "code": "E402",
        "message": "Module level import not at top of file",
        "location": {"row": 5, "column": 1},
    }
    data.update(overrides)
    return data


# ---- rule code -> (category, severity) ------------------------------------


@pytest.mark.parametrize(
    "code, expected",
    [
        ("F821", ("bug", "high")),       # undefined name
        ("F811", ("bug", "high")),       # redefinition
        ("F401", ("bug", "medium")),     # other pyflakes rules
        ("B006", ("bug", "medium")),     # bugbear
        ("E501", ("quality", "low")),    # pycodestyle
        ("W291", ("quality", "low")),    # whitespace
        ("SIM108", ("quality", "low")),  # simplify
        ("", ("quality", "low")),        # no code at all
    ],
)
def test_rule_codes_are_classified(code, expected):
    assert ruff_runner._classify(code) == expected


# ---- running Ruff ---------------------------------------------------------


def test_item_fields_are_mapped_to_a_finding(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "pkg", "a.py")
    monkeypatch.setattr(ruff_runner.subprocess, "run", fake_run(json.dumps([item(path)])))

    findings = ruff_runner.run_ruff(str(tmp_path))

    assert findings == [
        {
            "tool": "ruff",
            "category": "quality",
            "severity": "low",
            "file_path": "pkg/a.py",
            "line": 5,
            "rule_id": "E402",
            "message": "Module level import not at top of file",
        }
    ]


def test_undefined_name_becomes_a_high_severity_bug(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "a.py")
    output = json.dumps([item(path, code="F821", message="Undefined name `x`")])
    monkeypatch.setattr(ruff_runner.subprocess, "run", fake_run(output))

    finding = ruff_runner.run_ruff(str(tmp_path))[0]

    assert (finding["category"], finding["severity"]) == ("bug", "high")
    assert finding["rule_id"] == "F821"


@pytest.mark.parametrize("stdout", ["", "[]"])
def test_no_issues_returns_empty_list(tmp_path, monkeypatch, stdout):
    monkeypatch.setattr(ruff_runner.subprocess, "run", fake_run(stdout))

    assert ruff_runner.run_ruff(str(tmp_path)) == []


def test_missing_location_gives_no_line_number(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "a.py")
    output = json.dumps([item(path, location=None)])
    monkeypatch.setattr(ruff_runner.subprocess, "run", fake_run(output))

    assert ruff_runner.run_ruff(str(tmp_path))[0]["line"] is None


def test_missing_code_is_treated_as_low_quality(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "a.py")
    output = json.dumps([item(path, code=None)])
    monkeypatch.setattr(ruff_runner.subprocess, "run", fake_run(output))

    finding = ruff_runner.run_ruff(str(tmp_path))[0]

    assert finding["rule_id"] == ""
    assert (finding["category"], finding["severity"]) == ("quality", "low")


def test_crash_exit_code_raises_with_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ruff_runner.subprocess, "run", fake_run("", returncode=2, stderr="ruff exploded")
    )

    with pytest.raises(RuntimeError, match="Ruff failed: ruff exploded"):
        ruff_runner.run_ruff(str(tmp_path))


def test_timeout_raises_runtime_error(tmp_path, monkeypatch):
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ruff", timeout=1)

    monkeypatch.setattr(ruff_runner.subprocess, "run", slow)

    with pytest.raises(RuntimeError, match="timed out"):
        ruff_runner.run_ruff(str(tmp_path))


def test_command_ignores_repo_config_and_selects_our_rules(tmp_path, monkeypatch):
    run = fake_run("[]")
    monkeypatch.setattr(ruff_runner.subprocess, "run", run)

    ruff_runner.run_ruff(str(tmp_path))

    cmd = run.calls[0]
    assert cmd[cmd.index("check") + 1] == str(tmp_path)
    assert "--isolated" in cmd      # the scanned repo's own settings must not apply
    assert "--exit-zero" in cmd     # "issues found" is not an error
    assert cmd[cmd.index("--select") + 1] == ruff_runner.RULES
    assert cmd[cmd.index("--output-format") + 1] == "json"