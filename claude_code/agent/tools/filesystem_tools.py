"""Backwards-compatible imports for the workspace-scoped filesystem tools."""

from claude_code.tools.filesystem_tools import (
    append_file,
    delete_file,
    edit_file,
    file_exists,
    list_directory,
    read_file,
    write_file,
)

__all__ = [
    "append_file",
    "delete_file",
    "edit_file",
    "file_exists",
    "list_directory",
    "read_file",
    "write_file",
]
