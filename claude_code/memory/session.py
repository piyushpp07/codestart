import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from claude_code.config import config
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)

def _session_file() -> Path:
    return Path(config["memory"]["db_path"]).parent / "current_session"


def _metadata_file() -> Path:
    return Path(config["memory"]["db_path"]).parent / "sessions.json"


def _load_metadata() -> dict[str, dict]:
    try:
        data = json.loads(_metadata_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_metadata(metadata: dict[str, dict]) -> None:
    path = _metadata_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def _touch_session(session_id: str) -> None:
    metadata = _load_metadata()
    existing = metadata.get(session_id, {})
    metadata[session_id] = {
        "title": existing.get("title", "New session"),
        "pinned": bool(existing.get("pinned", False)),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _save_metadata(metadata)

def get_current_session() -> str:
    session_file = _session_file()
    if session_file.exists():
        session_id = session_file.read_text().strip()
        _touch_session(session_id)
        logger.info(f"Resuming session: {session_id}")
        return session_id
    return new_session()

def new_session() -> str:
    session_id = str(uuid.uuid4())
    session_file = _session_file()
    session_file.parent.mkdir(exist_ok=True)
    session_file.write_text(session_id)
    _touch_session(session_id)
    logger.info(f"Started new session: {session_id}")
    return session_id

def switch_session(session_id: str) -> str:
    session_file = _session_file()
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(session_id)
    _touch_session(session_id)
    logger.info(f"Switched to session: {session_id}")
    return session_id


def rename_session(session_id: str, title: str) -> None:
    """Set a human-readable local title for a conversation."""
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Session title cannot be empty")
    metadata = _load_metadata()
    existing = metadata.get(session_id, {})
    metadata[session_id] = {
        "title": clean_title[:120],
        "pinned": bool(existing.get("pinned", False)),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _save_metadata(metadata)


def pin_session(session_id: str, pinned: bool) -> None:
    """Pin or unpin a local conversation in the session browser."""
    metadata = _load_metadata()
    existing = metadata.get(session_id, {})
    metadata[session_id] = {
        "title": existing.get("title", "New session"),
        "pinned": pinned,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _save_metadata(metadata)


def session_metadata(session_id: str) -> dict:
    return _load_metadata().get(session_id, {"title": "New session", "pinned": False})


def all_session_metadata() -> dict[str, dict]:
    return _load_metadata()
