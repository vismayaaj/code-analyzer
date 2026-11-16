import os
import re
import shutil
import stat
import subprocess
import tempfile

GITHUB_URL = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+?(\.git)?/?$")
CLONE_TIMEOUT = 120  # seconds


def validate_repo_url(url: str) -> str:
    url = url.strip()
    if not GITHUB_URL.match(url):
        raise ValueError("Only public GitHub URLs like https://github.com/user/repo are supported")
    return url


def clone_repo(url: str) -> str:
    """Shallow-clone a public repo into a temp folder and return its path."""
    url = validate_repo_url(url)
    dest = tempfile.mkdtemp(prefix="analyzer_")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # never ask for passwords
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", url, dest],
            capture_output=True, text=True, timeout=CLONE_TIMEOUT, env=env,
        )
    except subprocess.TimeoutExpired:
        cleanup(dest)
        raise RuntimeError("Cloning timed out")
    if result.returncode != 0:
        cleanup(dest)
        raise RuntimeError(f"Clone failed: {result.stderr.strip()}")
    return dest


def _force_remove(func, path, _exc):
    # Windows marks .git files read-only; make them writable and retry
    os.chmod(path, stat.S_IWRITE)
    func(path)


def cleanup(path: str) -> None:
    shutil.rmtree(path, onerror=_force_remove)