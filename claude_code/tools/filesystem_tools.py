"""Workspace-scoped filesystem tools exposed to the coding agent."""

from pathlib import Path

from langchain.tools import tool

_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _workspace_root() -> Path:
    return Path.cwd().resolve()


def _resolve_workspace_path(file_path: str) -> Path | str:
    """Resolve a user path and reject paths outside the current workspace."""
    if not file_path or not file_path.strip():
        return "Error: file path cannot be empty"

    supplied = Path(file_path).expanduser()
    candidate = supplied if supplied.is_absolute() else _workspace_root() / supplied
    resolved = candidate.resolve()
    try:
        resolved.relative_to(_workspace_root())
    except ValueError:
        return f"Error: path must stay inside workspace: {_workspace_root()}"
    return resolved


@tool
def read_file(file_path: str) -> str:
    """Read a UTF-8 text file inside the current workspace."""
    resolved = _resolve_workspace_path(file_path)
    if isinstance(resolved, str):
        return resolved
    if not resolved.exists():
        return f"Error: file not found: {file_path}"
    if not resolved.is_file():
        return f"Error: path is not a file: {file_path}"
    size = resolved.stat().st_size
    if size > _MAX_FILE_SIZE_BYTES:
        return f"Error: file too large ({size} bytes). Max allowed is {_MAX_FILE_SIZE_BYTES} bytes"
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: file is not valid UTF-8 text: {file_path}"
    except OSError as exc:
        return f"Error: {exc}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Write a UTF-8 text file inside the current workspace."""
    resolved = _resolve_workspace_path(file_path)
    if isinstance(resolved, str):
        return resolved
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Written to {resolved}"
    except OSError as exc:
        return f"Error: {exc}"


@tool
def edit_file(file_path: str, old_text: str, new_text: str) -> str:
    """Replace one exact text block in a UTF-8 file inside the current workspace."""
    resolved = _resolve_workspace_path(file_path)
    if isinstance(resolved, str):
        return resolved
    if not old_text:
        return "Error: old_text cannot be empty"
    if not resolved.exists():
        return f"Error: file not found: {file_path}"
    if not resolved.is_file():
        return f"Error: path is not a file: {file_path}"
    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: file is not valid UTF-8 text: {file_path}"
    except OSError as exc:
        return f"Error: {exc}"

    occurrences = content.count(old_text)
    if occurrences == 0:
        return "Error: old_text was not found in the file"
    if occurrences > 1:
        return "Error: old_text occurs more than once; provide a more specific block"
    try:
        resolved.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {resolved}"
    except OSError as exc:
        return f"Error: {exc}"


@tool
def append_file(file_path: str, content: str) -> str:
    """Append text to an existing UTF-8 file inside the current workspace."""
    resolved = _resolve_workspace_path(file_path)
    if isinstance(resolved, str):
        return resolved
    if not resolved.exists():
        return f"Error: file not found: {file_path}"
    if not resolved.is_file():
        return f"Error: path is not a file: {file_path}"
    try:
        with resolved.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return f"Appended to {resolved}"
    except OSError as exc:
        return f"Error: {exc}"


@tool
def delete_file(file_path: str) -> str:
    """Delete a file inside the current workspace. Directories are never deleted."""
    resolved = _resolve_workspace_path(file_path)
    if isinstance(resolved, str):
        return resolved
    if not resolved.exists():
        return f"Error: file not found: {file_path}"
    if not resolved.is_file():
        return "Error: path is not a file (use a directory tool for directories)"
    try:
        resolved.unlink()
        return f"Deleted {resolved}"
    except OSError as exc:
        return f"Error: {exc}"


@tool
def list_directory(directory: str) -> str:
    """List files and subdirectories inside a workspace directory."""
    resolved = _resolve_workspace_path(directory)
    if isinstance(resolved, str):
        return resolved.replace("file path", "directory")
    if not resolved.exists():
        return f"Error: directory not found: {directory}"
    if not resolved.is_dir():
        return f"Error: path is not a directory: {directory}"
    try:
        entries = sorted(entry.name for entry in resolved.iterdir())
        return "\n".join(entries) if entries else "(empty directory)"
    except OSError as exc:
        return f"Error: {exc}"


@tool
def file_exists(file_path: str) -> str:
    """Check whether a workspace file or directory exists."""
    resolved = _resolve_workspace_path(file_path)
    if isinstance(resolved, str):
        return resolved
    return str(resolved.exists())
