import os
import stat
import subprocess
from types import SimpleNamespace

import pytest

from app.analyzers import repo


# ---- URL validation -------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/pallets/flask",
        "https://github.com/pallets/flask/",
        "https://github.com/pallets/flask.git",
        "https://github.com/pallets/flask.git/",
        "https://github.com/some-user/my.repo_name",
        "https://github.com/vismayaaj/vuln-test1",
    ],
)
def test_valid_github_urls_are_accepted_unchanged(url):
    assert repo.validate_repo_url(url) == url


def test_surrounding_whitespace_is_stripped():
    assert repo.validate_repo_url("  https://github.com/o/r \n") == "https://github.com/o/r"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/o/r",                     # not https
        "ftp://github.com/o/r",                      # wrong scheme
        "https://gitlab.com/o/r",                    # wrong host
        "https://github.com/onlyowner",              # no repo name
        "https://github.com/o/r/tree/main",          # extra path
        "https://github.com/o/r?tab=readme",         # query string
        "https://github.com/o/r with space",         # whitespace inside
        "git@github.com:o/r.git",                    # ssh form
        "https://evil.com/https://github.com/o/r",   # github url hidden in a path
        "https://github.com.evil.com/o/r",           # look-alike host
        "--upload-pack=touch /tmp/x",                # git option injection attempt
        "",
    ],
)
def test_invalid_urls_are_rejected(url):
    with pytest.raises(ValueError, match="Only public GitHub URLs"):
        repo.validate_repo_url(url)


# ---- cloning --------------------------------------------------------------


@pytest.fixture()
def clone_dir(tmp_path, monkeypatch):
    """Make clone_repo use a known temp folder instead of a random one."""
    path = tmp_path / "clone"

    def fake_mkdtemp(prefix=""):
        path.mkdir()
        return str(path)

    monkeypatch.setattr(repo.tempfile, "mkdtemp", fake_mkdtemp)
    return path


def fake_git(returncode=0, stderr="", raises=None):
    calls = []

    def _run(cmd, *args, **kwargs):
        calls.append((cmd, kwargs))
        if raises:
            raise raises
        return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")

    _run.calls = calls
    return _run


def test_clone_rejects_invalid_url_before_running_git(monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("git must not run for an invalid URL")

    monkeypatch.setattr(repo.subprocess, "run", must_not_run)

    with pytest.raises(ValueError):
        repo.clone_repo("https://evil.com/o/r")


def test_clone_is_shallow_and_never_prompts_for_passwords(monkeypatch, clone_dir):
    run = fake_git()
    monkeypatch.setattr(repo.subprocess, "run", run)

    result = repo.clone_repo("https://github.com/o/r")

    cmd, kwargs = run.calls[0]
    assert cmd[:4] == ["git", "clone", "--depth", "1"]
    assert "https://github.com/o/r" in cmd
    assert cmd[-1] == str(clone_dir)
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["timeout"] == repo.CLONE_TIMEOUT
    assert result == str(clone_dir)
    assert clone_dir.exists()


def test_failed_clone_raises_and_removes_the_temp_folder(monkeypatch, clone_dir):
    monkeypatch.setattr(
        repo.subprocess, "run", fake_git(returncode=128, stderr="fatal: repository not found")
    )

    with pytest.raises(RuntimeError, match="Clone failed: fatal: repository not found"):
        repo.clone_repo("https://github.com/o/r")

    assert not clone_dir.exists()


def test_clone_timeout_raises_and_removes_the_temp_folder(monkeypatch, clone_dir):
    monkeypatch.setattr(
        repo.subprocess, "run", fake_git(raises=subprocess.TimeoutExpired(cmd="git", timeout=1))
    )

    with pytest.raises(RuntimeError, match="timed out"):
        repo.clone_repo("https://github.com/o/r")

    assert not clone_dir.exists()


# ---- cleanup --------------------------------------------------------------


def test_cleanup_removes_a_folder_that_contains_read_only_files(tmp_path):
    folder = tmp_path / "analyzer_x"
    (folder / "sub").mkdir(parents=True)
    locked = folder / "sub" / "locked.txt"
    locked.write_text("x")
    os.chmod(locked, stat.S_IREAD)  # git marks some files like this on Windows

    repo.cleanup(str(folder))

    assert not folder.exists()