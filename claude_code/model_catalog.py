"""Fetch chat-model choices using a provider key without exposing the key."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from claude_code.settings import PROVIDERS

_TIMEOUT_SECONDS = 12


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed provider URLs only
        data = json.loads(response.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _catalog_response(provider: str, message: str, status: str = "catalog") -> dict[str, Any]:
    return {"models": PROVIDERS[provider]["models"], "source": status, "message": message}


def _provider_key(provider: str) -> str | None:
    key_name = PROVIDERS[provider]["key_env"]
    return os.getenv(key_name) if key_name else None


def _openai_models(key: str) -> list[str]:
    payload = _get_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
    return sorted({str(item.get("id")) for item in payload.get("data", []) if item.get("id")})


def _gemini_models(key: str) -> list[str]:
    models: set[str] = set()
    page_token = ""
    for _ in range(10):
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
        if page_token:
            url = f"{url}&pageToken={page_token}"
        payload = _get_json(url, {"x-goog-api-key": key})
        for item in payload.get("models", []):
            methods = item.get("supportedGenerationMethods", [])
            name = str(item.get("name", "")).removeprefix("models/")
            if name and "generateContent" in methods:
                models.add(name)
        page_token = str(payload.get("nextPageToken", ""))
        if not page_token:
            break
    return sorted(models)


def _anthropic_models(key: str) -> list[str]:
    payload = _get_json(
        "https://api.anthropic.com/v1/models",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    return sorted({str(item.get("id")) for item in payload.get("data", []) if item.get("id")})


def _ollama_models() -> list[str]:
    payload = _get_json("http://127.0.0.1:11434/api/tags")
    return sorted({str(item.get("name")) for item in payload.get("models", []) if item.get("name")})


def available_models(provider: str) -> dict[str, Any]:
    """Get models accessible to the configured account, with a safe local fallback."""
    normalized = provider.strip().lower()
    if normalized not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    if normalized == "ollama":
        try:
            models = _ollama_models()
            if models:
                return {"models": models, "source": "live", "message": "Loaded from local Ollama."}
            return _catalog_response(normalized, "Ollama is running but has no installed models.")
        except (HTTPError, URLError, OSError, ValueError):
            return _catalog_response(normalized, "Could not reach local Ollama. Start it, then refresh.")

    key = _provider_key(normalized)
    if not key:
        return _catalog_response(normalized, "Save an API key for this provider, then refresh to load account models.", "needs_key")

    fetchers = {"openai": _openai_models, "gemini": _gemini_models, "anthropic": _anthropic_models}
    try:
        models = fetchers[normalized](key)
        if models:
            return {"models": models, "source": "live", "message": "Loaded from the provider using your local key."}
        return _catalog_response(normalized, "The provider returned no chat models; showing suggested models.")
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
        return _catalog_response(normalized, "Could not load account models; showing suggested models.")
