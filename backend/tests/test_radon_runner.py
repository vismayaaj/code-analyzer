import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from app.analyzers import radon_runner


def fake_run(stdout, returncode=0, stderr=""):
    def _run(*args, **kwargs):
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return _run


def block(rank, complexity=20, name="work", lineno=3):
    return {
        "type": "function",
        "name": name,
        "complexity": complexity,
        "rank": rank,
        "lineno": lineno,
    }


def test_rank_maps_to_severity(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "a.py")
    output = {path: [block("C"), block("D"), block("E")]}
    monkeypatch.setattr(radon_runner.subprocess, "run", fake_run(json.dumps(output)))

    findings = radon_runner.run_radon(str(tmp_path))

    assert [f["severity"] for f in findings] == ["low", "medium", "high"]
    assert [f["rule_id"] for f in findings] == ["CC-C", "CC-D", "CC-E"]


def test_simple_functions_are_not_reported(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "a.py")
    output = {path: [block("A", complexity=2), block("B", complexity=7)]}
    monkeypatch.setattr(radon_runner.subprocess, "run", fake_run(json.dumps(output)))

    assert radon_runner.run_radon(str(tmp_path)) == []


def test_file_paths_are_relative_with_forward_slashes(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "pkg", "b.py")
    output = {path: [block("C")]}
    monkeypatch.setattr(radon_runner.subprocess, "run", fake_run(json.dumps(output)))

    findings = radon_runner.run_radon(str(tmp_path))

    assert findings[0]["file_path"] == "pkg/b.py"
    assert findings[0]["tool"] == "radon"
    assert findings[0]["category"] == "complexity"


def test_per_file_error_entries_are_skipped(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "broken.py")
    output = {path: {"error": "invalid syntax"}}
    monkeypatch.setattr(radon_runner.subprocess, "run", fake_run(json.dumps(output)))

    assert radon_runner.run_radon(str(tmp_path)) == []


def test_tool_failure_raises_runtime_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        radon_runner.subprocess, "run", fake_run("", returncode=1, stderr="radon crashed")
    )

    with pytest.raises(RuntimeError, match="Radon failed"):
        radon_runner.run_radon(str(tmp_path))


def test_timeout_raises_runtime_error(tmp_path, monkeypatch):
    def slow_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="radon", timeout=1)

    monkeypatch.setattr(radon_runner.subprocess, "run", slow_run)

    with pytest.raises(RuntimeError, match="timed out"):
        radon_runner.run_radon(str(tmp_path))