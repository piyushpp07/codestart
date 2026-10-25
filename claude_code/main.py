"""Interactive CLI for planning, staging, reviewing, and applying code changes."""

import asyncio
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from claude_code.agent.orchestrator import handle_query
from claude_code.changes import get_change_manager
from claude_code.config import config
from claude_code.context.indexers.factory import get_index_loader, get_indexer
from claude_code.context.indexers.code_parser import get_source_files
from claude_code.context.indexers.semantic_indexer import index_codebase as index_local_codebase
from claude_code.memory.session import (
    all_session_metadata,
    get_current_session,
    new_session,
    pin_session,
    rename_session,
    session_metadata,
    switch_session,
)
from claude_code.memory.short_term import (
    clear_session_history,
    close_checkpointer,
    get_session_history,
    list_session_ids,
)
from claude_code.observability.logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()
console = Console()
logger = get_logger(__name__)


def _is_cloud_provider(provider: str) -> bool:
    return provider in {"pinecone", "pinecone_hybrid", "hybrid_pinecone", "hybrid"}


def get_vectorstore_provider() -> str:
    return config.get("vectorstore", {}).get("provider", "faiss").lower()


def get_or_create_index(force: bool = False):
    """Synchronize the configured index; FAISS updates only files whose hashes changed."""
    provider = get_vectorstore_provider()
    repo_path = str(Path.cwd())
    if not _is_cloud_provider(provider):
        try:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                "{task.completed}/{task.total}",
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task_id = progress.add_task("Synchronizing local index", total=1)

                def update_progress(completed: int, total: int, description: str) -> None:
                    progress.update(task_id, completed=completed, total=max(total, 1), description=description)

                return index_local_codebase(
                    repo_path, force=force, progress_callback=update_progress
                )
        except Exception as exc:
            logger.warning("Local indexing failed: %s", exc)
            console.print(f"[yellow]Notice: {exc}. Running without an index.[/yellow]")
            return None

    index_codebase = get_indexer(provider)
    load_index = get_index_loader(provider)
    console.print(f"[dim]Connecting & indexing {repo_path} with Pinecone Cloud...[/dim]")
    try:
        return index_codebase(repo_path)
    except Exception as exc:
        logger.warning("Cloud indexing failed: %s", exc)
        console.print(f"[yellow]Notice: {exc}. Connecting to cloud index...[/yellow]")
        try:
            return load_index()
        except Exception as load_error:
            logger.warning("Could not connect to cloud index: %s", load_error)
            return None


def show_semantic_index(vectorstore) -> None:
    """Display all documents stored in the current index."""
    if not vectorstore:
        console.print("\n[yellow]No index active or 0 chunks indexed.[/yellow]\n")
        return
    if not hasattr(vectorstore, "index") or not hasattr(vectorstore.index, "ntotal"):
        console.print("\n[bold green]Pinecone Cloud Vectorstore Active[/bold green]\n")
        return

    total = vectorstore.index.ntotal
    console.print(f"\n[bold]Semantic Index (FAISS) — {total} chunks[/bold]\n")
    docs = [vectorstore.docstore.search(doc_id) for doc_id in vectorstore.index_to_docstore_id.values()]
    for number, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        console.print(f"[bold cyan]── Chunk {number} ──────────────────────────[/bold cyan]")
        console.print(f"  File   : {meta.get('source', 'unknown')}")
        console.print(f"  Name   : {meta.get('name', 'unknown')} ({meta.get('type', 'block')})")
        console.print(f"  Lines  : {meta.get('start_line', '?')} - {meta.get('end_line', '?')}")
        console.print(f"  Code   :\n[dim]{doc.page_content[:300]}[/dim]\n")


def initialize():
    """Synchronize the index and open or create a conversation session."""
    provider = get_vectorstore_provider()
    is_cloud = _is_cloud_provider(provider)
    console.print(
        f"[dim]LLM (used for requests): {config['llm']['provider']} / {config['llm']['model']}[/dim]"
    )
    console.print(
        f"[dim]Embedder: {config['embeddings']['provider']} / {config['embeddings']['model']}[/dim]"
    )
    console.print(
        f"[dim]Vectorstore: {provider.upper()} (Cloud)[/dim]"
        if is_cloud
        else f"[dim]Vectorstore: {provider.upper()}[/dim]"
    )
    vectorstore = get_or_create_index()
    if vectorstore and hasattr(vectorstore, "index") and hasattr(vectorstore.index, "ntotal"):
        count = f"{vectorstore.index.ntotal} chunks indexed"
    elif vectorstore:
        count = "Cloud synchronized"
    else:
        count = "No source files indexed"
    session_id = get_current_session()
    console.print(f"[dim]Session: {session_id}[/dim]")
    console.print(f"[green]✓ Ready — {provider.upper()} ({count})[/green]\n")
    return vectorstore, session_id


def show_help() -> None:
    """Display the full command reference."""
    console.print("[yellow]Safe code workflow:[/yellow]")
    console.print("  [bold]/plan <task>[/bold] — read-only implementation plan")
    console.print("  [bold]/write <task>[/bold] — stage proposed code changes")
    console.print("  [bold]/diff[/bold] — preview staged edits")
    console.print("  [bold]/approve[/bold] — preview then confirm applying staged edits")
    console.print("  [bold]/apply[/bold] — write staged edits to disk")
    console.print("  [bold]/undo[/bold] — revert the last /apply in this session")
    console.print("  [bold]/test[/bold] — run detected Python or Node checks")
    console.print("  [bold]/review[/bold] — read-only review of staged or Git changes")
    console.print("\n[yellow]Codebase and sessions:[/yellow]")
    console.print("  [bold]/ask <question>[/bold] — inspect or ask about the codebase")
    console.print("  [bold]/dashboard[/bold] — show the interactive terminal status view")
    console.print("  [bold]/files \\[query][/bold] — browse indexed source files")
    console.print("  [bold]/open <path>[/bold] — preview a workspace file")
    console.print("  [bold]/index[/bold] — force a full index rebuild")
    console.print("  [bold]/show_semantic_index[/bold] — show indexed chunks")
    console.print("  [bold]/sessions[/bold] — list saved conversations")
    console.print("  [bold]/rename_session <title>[/bold] — give the current session a name")
    console.print("  [bold]/pin_session[/bold] or [bold]/unpin_session[/bold] — organize sessions")
    console.print("  [bold]/search_sessions <query>[/bold] — find a saved conversation")
    console.print("  [bold]/history \\[session_id][/bold] — show recent messages")
    console.print("  [bold]/new_session[/bold] — start a fresh conversation")
    console.print("  [bold]/switch <session_id>[/bold] — resume a conversation")
    console.print("  [bold]/clear_session \\[session_id][/bold] — erase a conversation")
    console.print("  [bold]/session[/bold] — show current session id")
    console.print("  [bold]/help[/bold] — show this help")
    console.print("  [bold]/exit[/bold] — quit")
    console.print("  [bold]codestart --dashboard[/bold] — launch the local web dashboard")
    console.print("\n[dim]Example: /plan Add JWT authentication to the Express API[/dim]")


def _command_argument(value: str, command: str) -> str:
    return value.removeprefix(command).strip()


def show_terminal_dashboard(vectorstore, session_id: str) -> None:
    """Render a compact Rich dashboard for the current interactive session."""
    chunks = vectorstore.index.ntotal if getattr(vectorstore, "index", None) else 0
    metadata = session_metadata(session_id)
    status = Table.grid(padding=(0, 2))
    status.add_row("Session", f"{metadata.get('title', 'New session')}\n[dim]{session_id}[/dim]")
    status.add_row("Index", f"{chunks} chunks · {get_vectorstore_provider().upper()}")
    status.add_row("Changes", "[yellow]Staged[/yellow]" if get_change_manager().has_staged_changes else "[green]Clean[/green]")
    commands = "[bold]/plan[/bold] → [bold]/write[/bold] → [bold]/diff[/bold] → [bold]/approve[/bold] → [bold]/test[/bold]"
    console.print(Panel(status, title="[bold cyan]CodeStart Dashboard[/bold cyan]", box=box.ROUNDED))
    console.print(Panel(commands, title="Workflow", border_style="blue"))


def show_files(query: str = "") -> None:
    """Render a searchable tree of indexable files in the workspace."""
    root = Path.cwd().resolve()
    filtered = [
        Path(file_path)
        for file_path in get_source_files(str(root))
        if query.lower() in str(Path(file_path).relative_to(root)).lower()
    ]
    if not filtered:
        console.print("[dim]No indexed source files matched.[/dim]")
        return
    tree = Tree(f"[bold cyan]{root.name}[/bold cyan]")
    nodes: dict[Path, Tree] = {Path("."): tree}
    for file_path in filtered[:250]:
        relative = file_path.relative_to(root)
        parent = Path(".")
        for part in relative.parts[:-1]:
            next_path = parent / part
            if next_path not in nodes:
                nodes[next_path] = nodes[parent].add(f"[blue]{part}[/blue]")
            parent = next_path
        nodes[parent].add(relative.name)
    if len(filtered) > 250:
        tree.add(f"[dim]… {len(filtered) - 250} more files[/dim]")
    console.print(tree)


def show_file(file_path: str) -> None:
    """Preview a workspace text file with syntax highlighting."""
    from claude_code.tools.filesystem_tools import _resolve_workspace_path

    resolved = _resolve_workspace_path(file_path)
    if isinstance(resolved, str):
        console.print(f"[yellow]{resolved}[/yellow]")
        return
    if not resolved.is_file():
        console.print(f"[yellow]File not found: {file_path}[/yellow]")
        return
    try:
        content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        console.print(f"[yellow]Could not read file: {exc}[/yellow]")
        return
    lexer = resolved.suffix.lstrip(".") or "text"
    console.print(Syntax(content[:30_000], lexer, line_numbers=True, word_wrap=False))


def _git_diff() -> str:
    """Read the local unstaged Git diff, without modifying Git state."""
    if not (Path.cwd() / ".git").exists():
        return "No staged changes and this workspace is not a Git repository."
    try:
        result = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--"],
            capture_output=True,
            check=False,
            cwd=Path.cwd(),
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Could not read Git diff: {exc}"
    if result.returncode != 0:
        return f"Could not read Git diff: {result.stderr.strip()}"
    return result.stdout or "No unstaged Git changes found."


def _validation_commands() -> list[list[str]]:
    """Choose common validation commands for the project in the current directory."""
    commands: list[list[str]] = []
    if (Path.cwd() / "pyproject.toml").exists():
        if importlib.util.find_spec("pytest"):
            commands.append([sys.executable, "-m", "pytest", "-q"])
        if importlib.util.find_spec("pyright"):
            commands.append([sys.executable, "-m", "pyright"])
        if importlib.util.find_spec("ruff"):
            commands.append([sys.executable, "-m", "ruff", "check", "."])
    package_json = Path.cwd() / "package.json"
    if package_json.exists() and shutil.which("npm"):
        try:
            scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, json.JSONDecodeError):
            scripts = {}
        for name in ("test", "lint", "typecheck"):
            if name in scripts:
                commands.append(["npm", "run", name])
    return commands


def run_validation() -> str:
    """Run project checks with bounded output and timeouts."""
    commands = _validation_commands()
    if not commands:
        return "No supported test commands were detected."
    reports = []
    for command in commands:
        label = " ".join(command)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                cwd=Path.cwd(),
                text=True,
                timeout=120,
            )
            output = (result.stdout + result.stderr).strip() or "(no output)"
            reports.append(f"$ {label}\n{output[:6000]}\nExit code: {result.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            reports.append(f"$ {label}\nError: {exc}")
    return "\n\n".join(reports)


async def show_sessions() -> None:
    session_ids = await list_session_ids()
    metadata = all_session_metadata()
    known_ids = list(dict.fromkeys([*session_ids, *metadata]))
    if not known_ids:
        console.print("[dim]No saved conversations yet.[/dim]")
        return
    current_session = get_current_session()
    rows = []
    for session_id in known_ids:
        details = metadata.get(session_id, {})
        rows.append(
            (
                not bool(details.get("pinned", False)),
                str(details.get("updated_at", "")),
                session_id,
                details,
            )
        )
    table = Table(title="Saved sessions", box=box.SIMPLE)
    table.add_column("Title")
    table.add_column("ID", style="dim")
    table.add_column("State")
    for _, _, session_id, details in sorted(rows, key=lambda row: (row[0], row[1]), reverse=False):
        marker = " [green](current)[/green]" if session_id == current_session else ""
        pin = "📌 " if details.get("pinned") else ""
        table.add_row(f"{pin}{details.get('title', 'New session')}", session_id, marker or "—")
    console.print(table)


async def show_history(session_id: str) -> None:
    history = await get_session_history(session_id)
    if not history:
        console.print("[dim]No saved messages in that session.[/dim]")
        return
    console.print(f"[bold]Recent messages for {session_id}:[/bold]")
    for message in history[-20:]:
        content = str(message["content"]).replace("\n", " ")
        console.print(f"  [cyan]{message['role']}[/cyan]: {content[:500]}")


async def run():
    logger.info("Starting CodeStart assistant")
    console.print("\n[bold blue]CodeStart[/bold blue] — local-first coding agent")
    vectorstore, session_id = initialize()
    memory_dir = Path(config["memory"]["db_path"]).parent
    memory_dir.mkdir(parents=True, exist_ok=True)
    command_completer = WordCompleter(
        [
            "/plan", "/write", "/diff", "/approve", "/apply", "/undo", "/test", "/review",
            "/ask", "/dashboard", "/files", "/open", "/index", "/sessions", "/history",
            "/rename_session", "/pin_session", "/unpin_session", "/search_sessions",
            "/new_session", "/switch", "/clear_session", "/session", "/help", "/exit",
        ],
        ignore_case=True,
    )
    prompt_session = PromptSession(
        history=FileHistory(str(memory_dir / "command_history")), completer=command_completer
    )
    console.print("Type [bold]'/help'[/bold] for commands or [bold]'/exit'[/bold] to quit\n")
    try:
        while True:
            try:
                user_input = await prompt_session.prompt_async("\033[1;32m> \033[0m")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                break
            clean_input = user_input.strip()
            if not clean_input:
                continue
            if clean_input.lower() in {"/exit", "/quit", "exit", "quit"}:
                console.print("[dim]Goodbye![/dim]")
                break
            if clean_input.startswith("/plan "):
                task = _command_argument(clean_input, "/plan ")
                if task:
                    console.print(f"[dim]Planning: {task}...[/dim]")
                    console.print(await handle_query(task, session_id, mode="read"))
                else:
                    console.print("[yellow]Please describe the task after /plan.[/yellow]")
            elif clean_input.startswith("/write "):
                task = _command_argument(clean_input, "/write ")
                if task:
                    console.print(f"[dim]Staging: {task}...[/dim]")
                    prompt = (
                        "The user explicitly authorized this code change. Inspect the relevant files, "
                        "then stage the implementation with the staging tools. Do not write to disk. "
                        f"Task: {task}"
                    )
                    console.print(await handle_query(prompt, session_id, mode="stage"))
                else:
                    console.print("[yellow]Please describe the change after /write.[/yellow]")
            elif clean_input == "/diff":
                console.print(get_change_manager().diff())
            elif clean_input == "/approve":
                diff = get_change_manager().diff()
                console.print(diff)
                if get_change_manager().has_staged_changes and Prompt.ask(
                    "Apply these staged changes?", choices=["apply", "cancel"], default="cancel"
                ) == "apply":
                    result = get_change_manager().apply()
                    console.print(result)
                    if result.startswith("Applied"):
                        vectorstore = get_or_create_index()
            elif clean_input == "/apply":
                result = get_change_manager().apply()
                console.print(result)
                if result.startswith("Applied"):
                    vectorstore = get_or_create_index()
            elif clean_input == "/undo":
                result = get_change_manager().undo()
                console.print(result)
                if result.startswith("Undid"):
                    vectorstore = get_or_create_index()
            elif clean_input == "/test":
                console.print(run_validation())
            elif clean_input == "/review":
                diff = get_change_manager().diff() if get_change_manager().has_staged_changes else _git_diff()
                if diff.startswith("No "):
                    console.print(diff)
                else:
                    prompt = (
                        "Review the following diff without modifying files. Identify correctness, security, "
                        "regression, and test-coverage issues; prioritize findings by severity.\n\n"
                        f"```diff\n{diff}\n```"
                    )
                    console.print(await handle_query(prompt, session_id, mode="read"))
            elif clean_input in {"/index", "/reindex"}:
                vectorstore = get_or_create_index(force=True)
                console.print("[green]Index rebuild complete.[/green]" if vectorstore else "[yellow]Index rebuild failed.[/yellow]")
            elif clean_input == "/dashboard":
                show_terminal_dashboard(vectorstore, session_id)
            elif clean_input.startswith("/files"):
                show_files(_command_argument(clean_input, "/files"))
            elif clean_input.startswith("/open "):
                file_path = _command_argument(clean_input, "/open ")
                if file_path:
                    show_file(file_path)
                else:
                    console.print("[yellow]Please provide a file path after /open.[/yellow]")
            elif clean_input.startswith(("/ask ", "ask ")):
                question = clean_input.removeprefix("/ask ").removeprefix("ask ").strip()
                if question:
                    console.print(await handle_query(question, session_id, mode="read"))
                else:
                    console.print("[yellow]Please provide a question after /ask.[/yellow]")
            elif clean_input in {"/show_semantic_index", "show_semantic_index"}:
                show_semantic_index(vectorstore)
            elif clean_input == "/new_session":
                session_id = new_session()
                console.print(f"[green]New session started: {session_id}[/green]")
            elif clean_input == "/sessions":
                await show_sessions()
            elif clean_input.startswith("/rename_session "):
                title = _command_argument(clean_input, "/rename_session ")
                try:
                    rename_session(session_id, title)
                    console.print("[green]Session renamed.[/green]")
                except ValueError as exc:
                    console.print(f"[yellow]{exc}[/yellow]")
            elif clean_input == "/pin_session":
                pin_session(session_id, True)
                console.print("[green]Session pinned.[/green]")
            elif clean_input == "/unpin_session":
                pin_session(session_id, False)
                console.print("[green]Session unpinned.[/green]")
            elif clean_input.startswith("/search_sessions "):
                query = _command_argument(clean_input, "/search_sessions ").lower()
                matches = [
                    (candidate_id, details)
                    for candidate_id, details in all_session_metadata().items()
                    if query in candidate_id.lower() or query in str(details.get("title", "")).lower()
                ]
                if not matches:
                    console.print("[dim]No matching sessions.[/dim]")
                else:
                    for candidate_id, details in matches:
                        console.print(f"  {details.get('title', 'New session')} — [dim]{candidate_id}[/dim]")
            elif clean_input.startswith("/history"):
                target = _command_argument(clean_input, "/history") or session_id
                await show_history(target)
            elif clean_input.startswith("/switch "):
                target = _command_argument(clean_input, "/switch ")
                if target:
                    session_id = switch_session(target)
                    console.print(f"[green]Switched to session: {session_id}[/green]")
                else:
                    console.print("[yellow]Please provide a session id after /switch.[/yellow]")
            elif clean_input.startswith("/clear_session"):
                target = _command_argument(clean_input, "/clear_session") or session_id
                await clear_session_history(target)
                if target == session_id:
                    session_id = new_session()
                console.print(f"[green]Cleared session: {target}[/green]")
            elif clean_input == "/session":
                console.print(f"[dim]Current session: {session_id}[/dim]")
            elif clean_input in {"/help", "help"}:
                show_help()
            else:
                console.print("[yellow]Unknown command.[/yellow]")
                show_help()
    finally:
        await close_checkpointer()


def main() -> None:
    """Sync entry point for the CLI."""
    if "--dashboard" in sys.argv:
        import uvicorn

        uvicorn.run("claude_code.dashboard:app", host="127.0.0.1", port=8000, reload=False)
        return
    asyncio.run(run())


if __name__ == "__main__":
    main()
