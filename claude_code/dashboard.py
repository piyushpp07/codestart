"""Local FastAPI backend for the browser dashboard."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from claude_code.agent.orchestrator import handle_query, reset_agents
from claude_code.changes import get_change_manager
from claude_code.code_graph import build_code_graph
from claude_code.config import config, reload_config
from claude_code.context.indexers.code_parser import get_source_files
from claude_code.context.indexers.semantic_indexer import index_codebase
from claude_code.main import _git_diff, run_validation
from claude_code.memory.session import (
    all_session_metadata,
    get_current_session,
    pin_session,
    rename_session,
    session_metadata,
    switch_session,
)
from claude_code.memory.short_term import close_checkpointer, get_session_history, list_session_ids
from claude_code.mcp.mcp_config import (
    public_mcp_servers,
    remove_custom_mcp_server,
    save_custom_mcp_server,
    set_preset_enabled,
)
from claude_code.model_catalog import available_models
from claude_code.git_service import commit_all, create_branch, git_overview, switch_branch
from claude_code.settings import provider_catalog, public_llm_settings, save_llm_settings
from claude_code.tools.filesystem_tools import _resolve_workspace_path

WORKSPACE = Path.cwd().resolve()
workspace_dashboard = WORKSPACE / "dashboard"
WEB_ROOT = workspace_dashboard if workspace_dashboard.exists() else Path(__file__).resolve().parent.parent / "dashboard"
DIST_ROOT = WEB_ROOT / "dist"

app = FastAPI(title="CodeStart Dashboard")


class ChatRequest(BaseModel):
    message: str
    mode: Literal["ask", "plan", "write", "execute"] = "ask"
    session_id: str | None = None


class SessionUpdate(BaseModel):
    session_id: str
    title: str | None = None
    pinned: bool | None = None


class LLMSettingsUpdate(BaseModel):
    provider: str
    model: str
    fallbacks: list[dict] = []
    api_key: str | None = None
    api_keys: list[str] | None = None


class MCPPresetUpdate(BaseModel):
    enabled: bool


class CustomMCPServerUpdate(BaseModel):
    name: str
    command: str
    args: list[str] = []
    env: dict[str, str] = {}


class GitBranchUpdate(BaseModel):
    name: str


class GitCommitUpdate(BaseModel):
    message: str


class WorkspaceUpdate(BaseModel):
    path: str


def _session_rows(checkpoint_ids: list[str]) -> list[dict]:
    metadata = all_session_metadata()
    ids = list(dict.fromkeys([*checkpoint_ids, *metadata]))
    rows = [
        {
            "id": session_id,
            "title": metadata.get(session_id, {}).get("title", "New session"),
            "pinned": bool(metadata.get(session_id, {}).get("pinned", False)),
            "updated_at": metadata.get(session_id, {}).get("updated_at", ""),
        }
        for session_id in ids
    ]
    return sorted(rows, key=lambda row: (not row["pinned"], row["updated_at"]), reverse=False)


@app.get("/api/status")
async def status() -> dict:
    persist_dir = Path(config["faiss"]["persist_dir"])
    manifest_path = persist_dir / f"{config['faiss']['index_name']}.manifest.json"
    file_count = 0
    try:
        file_count = len(json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {}))
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "workspace": str(WORKSPACE),
        "session_id": get_current_session(),
        "session": session_metadata(get_current_session()),
        "staged": get_change_manager().has_staged_changes,
        "indexed_files": file_count,
    }


@app.post("/api/workspace")
async def change_workspace(request: WorkspaceUpdate) -> dict:
    """Move this local dashboard to another folder and rebuild its local index."""
    global WORKSPACE

    raw_path = request.path.strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="Choose a workspace folder.")
    target = Path(raw_path).expanduser().resolve()
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=400, detail="Workspace folder does not exist.")
    if target == WORKSPACE:
        return {"workspace": str(WORKSPACE), "result": "This workspace is already open.", "indexed_files": 0}
    if get_change_manager().has_staged_changes:
        raise HTTPException(
            status_code=409,
            detail="Apply or discard staged changes before switching workspaces.",
        )

    try:
        await close_checkpointer()
        os.chdir(target)
        WORKSPACE = target
        reload_config()
        reset_agents()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Could not open workspace: {exc}") from exc

    try:
        index = await asyncio.to_thread(index_codebase, str(WORKSPACE), True)
        return {
            "workspace": str(WORKSPACE),
            "result": f"Opened {WORKSPACE.name} and indexed {index.index.ntotal} chunks.",
            "indexed_files": index.index.ntotal,
        }
    except Exception as exc:  # The folder is still usable for browsing if indexing is unavailable.
        return {
            "workspace": str(WORKSPACE),
            "result": f"Opened {WORKSPACE.name}. Indexing is not ready: {exc}",
            "indexed_files": 0,
        }


@app.get("/api/settings")
async def settings() -> dict:
    return {"current": public_llm_settings(), "providers": provider_catalog()}


@app.post("/api/settings")
async def update_settings(request: LLMSettingsUpdate) -> dict:
    try:
        settings = save_llm_settings(
            provider=request.provider,
            model=request.model,
            fallbacks=request.fallbacks,
            api_key=request.api_key,
            api_keys=request.api_keys,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    reset_agents()
    return {"current": settings, "providers": provider_catalog()}


@app.get("/api/providers/{provider}/models")
async def provider_models(provider: str) -> dict:
    """Query models available to the locally configured provider account."""
    try:
        return await asyncio.to_thread(available_models, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/tools")
async def tools() -> dict:
    """Return local tools and connected MCP metadata without secrets."""
    return {
        "core": [
            {"name": "Code search", "description": "Searches the indexed workspace."},
            {"name": "Files", "description": "Reads and stages workspace file changes."},
            {"name": "Terminal", "description": "Runs project commands only in execute mode."},
            {"name": "Review & tests", "description": "Reviews diffs and runs local checks."},
        ],
        "mcp_servers": public_mcp_servers(),
    }


@app.put("/api/tools/mcp/{name}")
async def update_mcp_preset(name: str, request: MCPPresetUpdate) -> dict:
    try:
        servers = set_preset_enabled(name, request.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    reset_agents()
    return {"mcp_servers": servers}


@app.post("/api/tools/mcp")
async def create_mcp_server(request: CustomMCPServerUpdate) -> dict:
    try:
        servers = save_custom_mcp_server(request.name, request.command, request.args, request.env)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    reset_agents()
    return {"mcp_servers": servers}


@app.delete("/api/tools/mcp/{name}")
async def delete_mcp_server(name: str) -> dict:
    try:
        servers = remove_custom_mcp_server(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    reset_agents()
    return {"mcp_servers": servers}


@app.get("/api/files")
async def files(query: str = Query(default="")) -> dict:
    source_files = get_source_files(str(WORKSPACE))
    filtered = [
        str(Path(path).relative_to(WORKSPACE))
        for path in source_files
        if query.lower() in str(Path(path).relative_to(WORKSPACE)).lower()
    ]
    return {"files": filtered[:500], "total": len(filtered)}


@app.get("/api/graph")
async def graph() -> dict:
    return await asyncio.to_thread(build_code_graph, str(WORKSPACE))


@app.get("/api/git")
async def git() -> dict:
    return await asyncio.to_thread(git_overview, str(WORKSPACE))


@app.post("/api/git/branches")
async def git_branch(request: GitBranchUpdate) -> dict:
    try:
        return await asyncio.to_thread(create_branch, str(WORKSPACE), request.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/git/checkout")
async def git_checkout(request: GitBranchUpdate) -> dict:
    try:
        return await asyncio.to_thread(switch_branch, str(WORKSPACE), request.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/git/commit")
async def git_commit(request: GitCommitUpdate) -> dict:
    try:
        return await asyncio.to_thread(commit_all, str(WORKSPACE), request.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/file")
async def file_contents(path: str) -> dict:
    resolved = _resolve_workspace_path(path)
    if isinstance(resolved, str) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found in workspace")
    try:
        return {"path": str(resolved.relative_to(WORKSPACE)), "content": resolved.read_text(encoding="utf-8")}
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/diff")
async def diff() -> dict:
    manager = get_change_manager()
    return {"diff": manager.diff(), "staged": manager.has_staged_changes}


@app.post("/api/apply")
async def apply() -> dict:
    result = get_change_manager().apply()
    if result.startswith("Applied"):
        await asyncio.to_thread(index_codebase, str(WORKSPACE))
    return {"result": result}


@app.post("/api/undo")
async def undo() -> dict:
    result = get_change_manager().undo()
    if result.startswith("Undid"):
        await asyncio.to_thread(index_codebase, str(WORKSPACE))
    return {"result": result}


@app.post("/api/index")
async def rebuild_index() -> dict:
    index = await asyncio.to_thread(index_codebase, str(WORKSPACE), True)
    return {"result": f"Indexed {index.index.ntotal} chunks."}


@app.post("/api/test")
async def test() -> dict:
    return {"result": await asyncio.to_thread(run_validation)}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    session_id = request.session_id or get_current_session()
    if request.mode == "write":
        prompt = (
            "The user explicitly authorized this code change. Inspect the relevant files, then stage "
            "the implementation with the staging tools. Do not write to disk. Task: "
            f"{message}"
        )
        mode = "stage"
    elif request.mode == "execute":
        prompt = (
            "The user explicitly confirmed an execute request and may have enabled trusted MCP tools. "
            "Use connected tools only when necessary for this task, describe external effects before taking "
            "them when practical, and keep all local file changes focused. Task: "
            f"{message}"
        )
        mode = "write"
    elif request.mode == "plan":
        prompt = f"Create a read-only implementation plan for: {message}"
        mode = "read"
    else:
        prompt = message
        mode = "read"
    answer = await handle_query(prompt, session_id, mode=mode)
    return {"answer": answer, "session_id": session_id, "staged": get_change_manager().has_staged_changes}


@app.post("/api/review")
async def review() -> dict:
    manager = get_change_manager()
    review_diff = manager.diff() if manager.has_staged_changes else _git_diff()
    if review_diff.startswith("No "):
        return {"answer": review_diff}
    prompt = (
        "Review the following diff without modifying files. Identify correctness, security, regression, "
        "and test-coverage issues; prioritize findings by severity.\n\n"
        f"```diff\n{review_diff}\n```"
    )
    return {"answer": await handle_query(prompt, get_current_session(), mode="read")}


@app.get("/api/sessions")
async def sessions() -> dict:
    return {"sessions": _session_rows(await list_session_ids()), "current": get_current_session()}


@app.get("/api/sessions/{session_id}/history")
async def history(session_id: str) -> dict:
    return {"messages": await get_session_history(session_id)}


@app.post("/api/sessions")
async def update_session(request: SessionUpdate) -> dict:
    if request.title is not None:
        rename_session(request.session_id, request.title)
    if request.pinned is not None:
        pin_session(request.session_id, request.pinned)
    return {"session": session_metadata(request.session_id)}


@app.post("/api/sessions/{session_id}/select")
async def select_session(session_id: str) -> dict:
    switch_session(session_id)
    return {"session_id": session_id}


@app.get("/")
async def dashboard_index():
    index_file = DIST_ROOT / "index.html"
    if not index_file.exists():
        return {
            "message": "Dashboard frontend has not been built.",
            "command": "cd dashboard && npm install && npm run build",
        }
    return FileResponse(index_file)


if DIST_ROOT.exists():
    app.mount("/", StaticFiles(directory=DIST_ROOT, html=True), name="dashboard-static")
