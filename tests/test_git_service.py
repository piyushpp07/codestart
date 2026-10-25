import subprocess
from pathlib import Path

from claude_code.git_service import create_branch, git_overview


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)


def test_git_overview_and_branch_creation(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "Initial")

    result = create_branch(str(tmp_path), "feature/graph")

    assert result["branch"] == "feature/graph"
    assert "main" in result["branches"]
    assert "feature/graph" in result["branches"]
    assert git_overview(str(tmp_path))["is_repo"] is True
