from pathlib import Path

from claude_code.changes import get_change_manager


def test_staged_changes_require_apply_and_can_be_undone(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "app.ts"
    source.write_text("export const value = 1;\n", encoding="utf-8")
    manager = get_change_manager()

    assert manager.stage_edit("app.ts", "value = 1", "value = 2").startswith("Staged edit")
    assert source.read_text(encoding="utf-8") == "export const value = 1;\n"
    assert "-export const value = 1;" in manager.diff()
    assert "+export const value = 2;" in manager.diff()

    assert manager.apply() == "Applied 1 file change(s)."
    assert source.read_text(encoding="utf-8") == "export const value = 2;\n"
    assert manager.undo() == "Undid 1 file change(s)."
    assert source.read_text(encoding="utf-8") == "export const value = 1;\n"


def test_staged_new_file_can_be_deleted_before_apply(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    manager = get_change_manager()

    assert manager.stage_write("new-file.ts", "export {};\n").startswith("Staged write")
    assert manager.stage_delete("new-file.ts").startswith("Staged deletion")
    assert not manager.has_staged_changes
