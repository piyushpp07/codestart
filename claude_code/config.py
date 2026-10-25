from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load root project .env first, then current working directory .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

DEFAULT_CONFIG = {
    "llm": {"provider": "gemini", "model": "gemini-2.5-flash", "fallbacks": []},
    "embeddings": {"provider": "fastembed", "model": "BAAI/bge-small-en-v1.5"},
    "vectorstore": {"provider": "faiss"},
    "faiss": {"persist_dir": ".faiss/", "index_name": "codebase"},
    "memory": {
        "db_path": ".memory/memory.db",
        "summarize_at_tokens": 4000,
        "keep_last_messages": 20,
    },
    "skills": {"skills_dir": ".claude_code/skills"},
}


def _merge_defaults(defaults: dict, supplied: dict) -> dict:
    """Recursively merge user configuration over the supported defaults."""
    merged = defaults.copy()
    for key, value in supplied.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict:
    """Load settings from config.yaml at the project root."""
    for base in [Path.cwd(), Path(__file__).resolve().parent.parent]:
        candidate = base / "config.yaml"
        if candidate.exists():
            contents = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            if not isinstance(contents, dict):
                raise ValueError(f"Configuration in {candidate} must be a YAML mapping")
            return _merge_defaults(DEFAULT_CONFIG, contents)
    return DEFAULT_CONFIG.copy()


config = load_config()
