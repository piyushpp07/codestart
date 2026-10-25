"""Local-only LLM provider, model, fallback, and API-key settings."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from claude_code.config import PROJECT_ROOT, config

PROVIDERS: dict[str, dict] = {
    "gemini": {
        "label": "Google Gemini",
        "key_env": "GOOGLE_API_KEY",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
    },
    "openai": {
        "label": "OpenAI",
        "key_env": "OPENAI_API_KEY",
        "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
    },
    "anthropic": {
        "label": "Anthropic",
        "key_env": "ANTHROPIC_API_KEY",
        "models": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
    },
    "ollama": {
        "label": "Ollama (local)",
        "key_env": None,
        "models": ["qwen2.5-coder:7b", "llama3.2", "deepseek-r1:8b"],
    },
}


def _config_path() -> Path:
    workspace_path = Path.cwd() / "config.yaml"
    return workspace_path if workspace_path.exists() else PROJECT_ROOT / "config.yaml"


def _env_path() -> Path:
    return Path.cwd() / ".env"


def provider_catalog() -> list[dict]:
    """Return public provider metadata without any secrets."""
    return [
        {
            "id": provider_id,
            "label": provider["label"],
            "models": provider["models"],
            "requires_api_key": provider["key_env"] is not None,
            "configured": bool(provider["key_env"] and os.getenv(provider["key_env"])),
        }
        for provider_id, provider in PROVIDERS.items()
    ]


def public_llm_settings() -> dict:
    llm = config["llm"]
    return {
        "provider": llm["provider"],
        "model": llm["model"],
        "fallbacks": llm.get("fallbacks", []),
    }


def _write_env_value(key: str, value: str) -> None:
    path = _env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    replacement = f"{key}={value}"
    if pattern.search(existing):
        updated = pattern.sub(replacement, existing)
    else:
        updated = f"{existing.rstrip()}\n{replacement}\n" if existing.strip() else f"{replacement}\n"
    path.write_text(updated, encoding="utf-8")
    os.environ[key] = value


def _validate_choice(provider: str, model: str) -> tuple[str, str]:
    normalized_provider = provider.strip().lower()
    normalized_model = model.strip()
    if normalized_provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    if not normalized_model:
        raise ValueError("A model name is required")
    return normalized_provider, normalized_model


def save_llm_settings(
    provider: str,
    model: str,
    fallbacks: list[dict] | None = None,
    api_key: str | None = None,
) -> dict:
    """Persist the selected model and optional local key; never return a key."""
    provider, model = _validate_choice(provider, model)
    normalized_fallbacks = []
    for fallback in fallbacks or []:
        fallback_provider, fallback_model = _validate_choice(
            str(fallback.get("provider", "")), str(fallback.get("model", ""))
        )
        if fallback_provider != provider:
            normalized_fallbacks.append({"provider": fallback_provider, "model": fallback_model})

    if api_key is not None and api_key.strip():
        key_env = PROVIDERS[provider]["key_env"]
        if key_env is None:
            raise ValueError("Ollama runs locally and does not use an API key")
        _write_env_value(key_env, api_key.strip())

    path = _config_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    raw = raw if isinstance(raw, dict) else {}
    raw["llm"] = {"provider": provider, "model": model, "fallbacks": normalized_fallbacks}
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    config["llm"] = raw["llm"]
    return public_llm_settings()
