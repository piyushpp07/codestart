"""Local-only LLM provider, model, fallback, and API-key pool settings."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

from claude_code.config import PROJECT_ROOT, config

PROVIDERS: dict[str, dict] = {
    "gemini": {
        "label": "Google Gemini",
        "key_env": "GOOGLE_API_KEY",
        "keys_env": "GOOGLE_API_KEYS",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
    },
    "openai": {
        "label": "OpenAI",
        "key_env": "OPENAI_API_KEY",
        "keys_env": "OPENAI_API_KEYS",
        "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
    },
    "anthropic": {
        "label": "Anthropic",
        "key_env": "ANTHROPIC_API_KEY",
        "keys_env": "ANTHROPIC_API_KEYS",
        "models": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
    },
    "ollama": {
        "label": "Ollama (local)",
        "key_env": None,
        "keys_env": None,
        "models": ["qwen2.5-coder:7b", "llama3.2", "deepseek-r1:8b"],
    },
}


def _config_path() -> Path:
    workspace_path = Path.cwd() / "config.yaml"
    return workspace_path if workspace_path.exists() else PROJECT_ROOT / "config.yaml"


def _env_path() -> Path:
    return Path.cwd() / ".env"


def _normalized_keys(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def provider_api_keys(provider: str) -> list[str]:
    """Read a provider's local key pool without returning it from public APIs."""
    details = PROVIDERS[provider]
    values: list[str] = []
    primary_key = details["key_env"]
    keys_env = details["keys_env"]
    if primary_key and os.getenv(primary_key):
        values.append(os.environ[primary_key])
    if keys_env and os.getenv(keys_env):
        raw = os.environ[keys_env]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                values.extend(str(item) for item in parsed)
            else:
                values.extend(raw.splitlines())
        except json.JSONDecodeError:
            values.extend(raw.splitlines())
    return _normalized_keys(values)


def provider_catalog() -> list[dict]:
    """Return public provider metadata and key counts without any secrets."""
    return [
        {
            "id": provider_id,
            "label": provider["label"],
            "models": provider["models"],
            "requires_api_key": provider["key_env"] is not None,
            "configured": bool(provider_api_keys(provider_id)),
            "key_count": len(provider_api_keys(provider_id)),
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
    api_keys: list[str] | None = None,
) -> dict:
    """Persist model routing and append local keys; never return any key values."""
    provider, model = _validate_choice(provider, model)
    normalized_fallbacks = []
    seen_fallbacks: set[tuple[str, str]] = {(provider, model)}
    for fallback in fallbacks or []:
        fallback_provider, fallback_model = _validate_choice(
            str(fallback.get("provider", "")), str(fallback.get("model", ""))
        )
        identity = (fallback_provider, fallback_model)
        if identity not in seen_fallbacks:
            normalized_fallbacks.append({"provider": fallback_provider, "model": fallback_model})
            seen_fallbacks.add(identity)

    incoming_keys = _normalized_keys(api_keys or [])
    if api_key and api_key.strip():
        incoming_keys.append(api_key.strip())
    incoming_keys = _normalized_keys(incoming_keys)
    if incoming_keys:
        details = PROVIDERS[provider]
        key_env = details["key_env"]
        keys_env = details["keys_env"]
        if key_env is None or keys_env is None:
            raise ValueError("Ollama runs locally and does not use an API key")
        all_keys = _normalized_keys([*provider_api_keys(provider), *incoming_keys])
        _write_env_value(key_env, all_keys[0])
        _write_env_value(keys_env, json.dumps(all_keys))

    path = _config_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    raw = raw if isinstance(raw, dict) else {}
    raw["llm"] = {"provider": provider, "model": model, "fallbacks": normalized_fallbacks}
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    config["llm"] = raw["llm"]
    return public_llm_settings()
