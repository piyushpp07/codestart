from claude_code import model_catalog


def test_openai_models_are_loaded_with_configured_local_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "local-key")
    monkeypatch.setattr(model_catalog, "_openai_models", lambda key: ["gpt-4.1", "gpt-4.1-mini"])

    result = model_catalog.available_models("openai")

    assert result == {
        "models": ["gpt-4.1", "gpt-4.1-mini"],
        "source": "live",
        "message": "Loaded from the provider using your local key.",
    }


def test_missing_key_uses_catalog_without_network(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = model_catalog.available_models("anthropic")

    assert result["source"] == "needs_key"
    assert result["models"]
    assert "API key" in result["message"]


def test_ollama_connection_failure_uses_suggested_models(monkeypatch) -> None:
    def fail() -> list[str]:
        raise OSError("offline")

    monkeypatch.setattr(model_catalog, "_ollama_models", fail)

    result = model_catalog.available_models("ollama")

    assert result["source"] == "catalog"
    assert "Ollama" in result["message"]
