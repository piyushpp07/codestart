from pathlib import Path
from typing import cast

import aiosqlite
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from claude_code.config import config
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)

_checkpointer: AsyncSqliteSaver | None = None
_connection: aiosqlite.Connection | None = None


async def get_checkpointer() -> AsyncSqliteSaver:
    """Return the process-wide SQLite checkpointer, creating it once."""
    global _checkpointer, _connection
    if _checkpointer is not None:
        return _checkpointer

    db_path = config["memory"]["db_path"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)  # create parent directory if not exists
    logger.info(f"Using checkpointer: {db_path}")
    _connection = await aiosqlite.connect(db_path)
    _checkpointer = AsyncSqliteSaver(_connection)
    await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer() -> None:
    """Close the cached SQLite connection during a clean CLI shutdown."""
    global _checkpointer, _connection
    if _connection is not None:
        await _connection.close()
    _connection = None
    _checkpointer = None


async def get_session_history(thread_id: str) -> list[dict]:
    checkpointer = await get_checkpointer()
    config_ = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    state = await checkpointer.aget(config_)
    if not state:
        return []
    messages = state["channel_values"].get("messages", [])
    return [
        {"role": "user" if m.type == "human" else "assistant", "content": m.content}
        for m in messages
    ]


async def list_session_ids(limit: int = 20) -> list[str]:
    """Return recently checkpointed conversation IDs without reading their contents."""
    checkpointer = await get_checkpointer()
    session_ids: list[str] = []
    seen: set[str] = set()
    async for checkpoint in checkpointer.alist(None, limit=limit * 10):
        thread_id = checkpoint.config.get("configurable", {}).get("thread_id")
        if isinstance(thread_id, str) and thread_id not in seen:
            session_ids.append(thread_id)
            seen.add(thread_id)
        if len(session_ids) >= limit:
            break
    return session_ids


async def clear_session_history(thread_id: str) -> None:
    """Delete one conversation's checkpoints from the local SQLite store."""
    checkpointer = await get_checkpointer()
    await checkpointer.adelete_thread(thread_id)
