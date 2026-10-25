"""LangChain tools that stage code changes without touching workspace files."""

from langchain.tools import tool

from claude_code.changes import get_change_manager


@tool
def stage_write_file(file_path: str, content: str) -> str:
    """Stage a complete UTF-8 file write. It will not reach disk until /apply."""
    return get_change_manager().stage_write(file_path, content)


@tool
def stage_edit_file(file_path: str, old_text: str, new_text: str) -> str:
    """Stage one exact replacement. It will not reach disk until /apply."""
    return get_change_manager().stage_edit(file_path, old_text, new_text)


@tool
def stage_delete_file(file_path: str) -> str:
    """Stage deletion of a workspace file. It will not reach disk until /apply."""
    return get_change_manager().stage_delete(file_path)


@tool
def show_staged_diff() -> str:
    """Show the unified diff for every code change staged in this session."""
    return get_change_manager().diff()
