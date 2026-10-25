"""Small, workspace-scoped Git operations used by the local dashboard."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_BRANCH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


def _run(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=workspace, text=True, capture_output=True, check=False, timeout=30)


def git_overview(workspace: str) -> dict:
    root = Path(workspace).resolve()
    if not (root / ".git").exists():
        return {"is_repo": False, "branches": [], "changes": [], "remotes": []}
    branch = _run(root, "branch", "--show-current").stdout.strip()
    branches = [line.strip().removeprefix("* ").strip() for line in _run(root, "branch", "--format=%(refname:short)").stdout.splitlines() if line.strip()]
    changes = [line for line in _run(root, "status", "--short").stdout.splitlines() if line]
    remotes = [line for line in _run(root, "remote", "-v").stdout.splitlines() if line]
    return {"is_repo": True, "branch": branch, "branches": branches, "changes": changes, "remotes": remotes}


def create_branch(workspace: str, name: str) -> dict:
    clean = name.strip()
    if not _BRANCH_NAME.fullmatch(clean) or ".." in clean or clean.endswith("/"):
        raise ValueError("Use a valid Git branch name")
    root = Path(workspace).resolve()
    result = _run(root, "switch", "-c", clean)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Could not create branch")
    return git_overview(workspace)


def switch_branch(workspace: str, name: str) -> dict:
    root = Path(workspace).resolve()
    result = _run(root, "switch", name)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Could not switch branch")
    return git_overview(workspace)


def commit_all(workspace: str, message: str) -> dict:
    clean = message.strip()
    if not clean:
        raise ValueError("A commit message is required")
    root = Path(workspace).resolve()
    staged = _run(root, "add", "-A")
    if staged.returncode:
        raise ValueError(staged.stderr.strip() or "Could not stage changes")
    result = _run(root, "commit", "-m", clean)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Could not create commit")
    return git_overview(workspace)
