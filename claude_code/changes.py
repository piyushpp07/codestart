"""In-memory staged edits used by the CLI's review-before-apply workflow."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

from claude_code.tools.filesystem_tools import _resolve_workspace_path


@dataclass
class StagedChange:
    """The before and after text for a single workspace file."""

    path: Path
    original: str | None
    replacement: str | None


class ChangeManager:
    """Stages text changes in memory, then applies or undoes them as one batch."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._staged: dict[Path, StagedChange] = {}
        self._last_applied: list[StagedChange] | None = None

    def _resolve(self, file_path: str) -> Path | str:
        resolved = _resolve_workspace_path(file_path)
        if isinstance(resolved, str):
            return resolved
        return resolved

    def _current_text(self, path: Path) -> str | None:
        change = self._staged.get(path)
        if change is not None:
            return change.replacement
        if not path.exists():
            return None
        if not path.is_file():
            raise IsADirectoryError(f"path is not a file: {path}")
        return path.read_text(encoding="utf-8")

    def _stage(self, path: Path, replacement: str | None) -> None:
        existing = self._staged.get(path)
        original = existing.original if existing is not None else self._current_text(path)
        if original == replacement:
            self._staged.pop(path, None)
            return
        self._staged[path] = StagedChange(path, original, replacement)

    def stage_write(self, file_path: str, content: str) -> str:
        resolved = self._resolve(file_path)
        if isinstance(resolved, str):
            return resolved
        try:
            self._stage(resolved, content)
        except (OSError, UnicodeDecodeError) as exc:
            return f"Error: {exc}"
        return f"Staged write for {resolved.relative_to(self.root)}"

    def stage_edit(self, file_path: str, old_text: str, new_text: str) -> str:
        if not old_text:
            return "Error: old_text cannot be empty"
        resolved = self._resolve(file_path)
        if isinstance(resolved, str):
            return resolved
        try:
            current = self._current_text(resolved)
        except (OSError, UnicodeDecodeError) as exc:
            return f"Error: {exc}"
        if current is None:
            return f"Error: file not found: {file_path}"
        occurrences = current.count(old_text)
        if occurrences == 0:
            return "Error: old_text was not found in the current staged file"
        if occurrences > 1:
            return "Error: old_text occurs more than once; provide a more specific block"
        self._stage(resolved, current.replace(old_text, new_text, 1))
        return f"Staged edit for {resolved.relative_to(self.root)}"

    def stage_delete(self, file_path: str) -> str:
        resolved = self._resolve(file_path)
        if isinstance(resolved, str):
            return resolved
        try:
            if self._current_text(resolved) is None:
                return f"Error: file not found: {file_path}"
            self._stage(resolved, None)
        except (OSError, UnicodeDecodeError) as exc:
            return f"Error: {exc}"
        return f"Staged deletion for {resolved.relative_to(self.root)}"

    def diff(self) -> str:
        """Return a unified diff of all staged changes."""
        if not self._staged:
            return "No staged changes. Use /write <task> first."
        chunks = []
        for change in self._staged.values():
            relative = str(change.path.relative_to(self.root))
            before = (change.original or "").splitlines(keepends=True)
            after = (change.replacement or "").splitlines(keepends=True)
            chunks.extend(
                unified_diff(before, after, fromfile=f"a/{relative}", tofile=f"b/{relative}")
            )
        return "".join(chunks) or "No staged changes."

    def apply(self) -> str:
        """Apply all staged changes and remember one transaction for /undo."""
        if not self._staged:
            return "No staged changes to apply."
        changes = list(self._staged.values())
        applied: list[StagedChange] = []
        try:
            for change in changes:
                if change.replacement is None:
                    if change.path.exists():
                        change.path.unlink()
                else:
                    change.path.parent.mkdir(parents=True, exist_ok=True)
                    change.path.write_text(change.replacement, encoding="utf-8")
                applied.append(change)
        except OSError as exc:
            for change in reversed(applied):
                if change.original is None:
                    if change.path.exists():
                        change.path.unlink()
                else:
                    change.path.write_text(change.original, encoding="utf-8")
            return f"Error applying staged changes: {exc}"
        self._last_applied = changes
        self._staged.clear()
        return f"Applied {len(changes)} file change(s)."

    def undo(self) -> str:
        """Restore the most recent applied batch during this CLI session."""
        if not self._last_applied:
            return "Nothing to undo in this session."
        try:
            for change in self._last_applied:
                if change.original is None:
                    if change.path.exists():
                        change.path.unlink()
                else:
                    change.path.parent.mkdir(parents=True, exist_ok=True)
                    change.path.write_text(change.original, encoding="utf-8")
        except OSError as exc:
            return f"Error undoing changes: {exc}"
        count = len(self._last_applied)
        self._last_applied = None
        return f"Undid {count} file change(s)."

    @property
    def has_staged_changes(self) -> bool:
        return bool(self._staged)


_manager: ChangeManager | None = None


def get_change_manager() -> ChangeManager:
    """Return one change manager per workspace process."""
    global _manager
    root = Path.cwd().resolve()
    if _manager is None or _manager.root != root:
        _manager = ChangeManager(root)
    return _manager
