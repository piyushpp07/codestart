from pathlib import Path

from claude_code.tools.filesystem_tools import (
    append_file,
    edit_file,
    file_exists,
    read_file,
    write_file,
)


def test_filesystem_tools_are_scoped_to_current_workspace(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    assert write_file.invoke({"file_path": "notes/todo.txt", "content": "one"}).startswith("Written")
    assert append_file.invoke({"file_path": "notes/todo.txt", "content": " two"}).startswith("Appended")
    assert edit_file.invoke(
        {"file_path": "notes/todo.txt", "old_text": "one two", "new_text": "done"}
    ).startswith("Edited")
    assert read_file.invoke({"file_path": "notes/todo.txt"}) == "done"
    assert file_exists.invoke({"file_path": "notes/todo.txt"}) == "True"
    assert "must stay inside workspace" in read_file.invoke({"file_path": "../outside.txt"})
