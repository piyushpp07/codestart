"""Coverage for safely moving the local dashboard between project folders."""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

from claude_code import dashboard
from claude_code.config import reload_config


def test_change_workspace_reloads_local_context(tmp_path: Path, monkeypatch) -> None:
    original_cwd = Path.cwd()
    original_workspace = dashboard.WORKSPACE
    target = tmp_path / "react-app"
    target.mkdir()

    async def close_memory() -> None:
        return None

    monkeypatch.setattr(dashboard, "close_checkpointer", close_memory)
    monkeypatch.setattr(
        dashboard,
        "index_codebase",
        lambda path, force: SimpleNamespace(index=SimpleNamespace(ntotal=7)),
    )

    try:
        response = asyncio.run(
            dashboard.change_workspace(dashboard.WorkspaceUpdate(path=str(target)))
        )
        assert response["workspace"] == str(target)
        assert response["indexed_files"] == 7
        assert dashboard.WORKSPACE == target
        assert Path.cwd() == target
    finally:
        os.chdir(original_cwd)
        dashboard.WORKSPACE = original_workspace
        reload_config()
