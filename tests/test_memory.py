import asyncio
from pathlib import Path

from claude_code.config import config
from claude_code.memory import short_term


def test_checkpointer_is_cached_and_can_read_an_empty_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(config, "memory", {"db_path": str(tmp_path / "memory.db")})

    async def exercise_checkpointer() -> None:
        await short_term.close_checkpointer()
        first = await short_term.get_checkpointer()
        second = await short_term.get_checkpointer()

        assert first is second
        assert await short_term.get_session_history("unknown-session") == []
        await short_term.close_checkpointer()

    asyncio.run(exercise_checkpointer())
