from copy import deepcopy
from pathlib import Path

from claude_code.config import config
from claude_code.llm import factory
from claude_code.settings import save_llm_settings


def test_settings_save_key_locally_without_returning_it(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEYS", raising=False)
    (tmp_path / "config.yaml").write_text("llm:\n  provider: gemini\n  model: old\n", encoding="utf-8")
    original = deepcopy(config)
    try:
        saved = save_llm_settings(
            provider="openai",
            model="gpt-4.1-mini",
            fallbacks=[{"provider": "gemini", "model": "gemini-2.5-flash"}],
            api_key="top-secret",
        )
        assert saved["provider"] == "openai"
        assert saved["fallbacks"] == [{"provider": "gemini", "model": "gemini-2.5-flash"}]
        assert "top-secret" not in str(saved)
        assert "OPENAI_API_KEY=top-secret" in (tmp_path / ".env").read_text(encoding="utf-8")
        assert 'OPENAI_API_KEYS=["top-secret"]' in (tmp_path / ".env").read_text(encoding="utf-8")
        assert "provider: openai" in (tmp_path / "config.yaml").read_text(encoding="utf-8")
    finally:
        config.clear()
        config.update(original)


def test_settings_append_key_pool_without_public_key_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEYS", raising=False)
    (tmp_path / "config.yaml").write_text("llm:\n  provider: openai\n  model: gpt-4.1-mini\n", encoding="utf-8")
    original = deepcopy(config)
    try:
        saved = save_llm_settings(
            provider="openai",
            model="gpt-4.1-mini",
            api_keys=["key-one", "key-two", "key-one"],
        )
        stored = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "OPENAI_API_KEY=key-one" in stored
        assert 'OPENAI_API_KEYS=["key-one", "key-two"]' in stored
        assert "key-one" not in str(saved)
        assert "key-two" not in str(saved)
    finally:
        config.clear()
        config.update(original)


def test_llm_factory_wraps_configured_fallbacks(monkeypatch) -> None:
    class FakeModel:
        def __init__(self, name: str) -> None:
            self.name = name

        def with_fallbacks(self, fallbacks):
            return {"primary": self.name, "fallbacks": [fallback.name for fallback in fallbacks]}

    original = deepcopy(config)
    monkeypatch.setattr(factory, "_build_llm", lambda provider, model, api_key=None: FakeModel(f"{provider}/{model}/{api_key or 'default'}"))
    monkeypatch.setattr(factory, "provider_api_keys", lambda provider: [])
    try:
        config["llm"] = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "fallbacks": [{"provider": "openai", "model": "gpt-4.1-mini"}],
        }
        assert factory.get_llm() == {
            "primary": "gemini/gemini-2.5-flash/default",
            "fallbacks": ["openai/gpt-4.1-mini/default"],
        }
    finally:
        config.clear()
        config.update(original)


def test_llm_factory_tries_extra_keys_before_fallback_models(monkeypatch) -> None:
    class FakeModel:
        def __init__(self, name: str) -> None:
            self.name = name

        def with_fallbacks(self, fallbacks):
            return {"primary": self.name, "fallbacks": [fallback.name for fallback in fallbacks]}

    original = deepcopy(config)
    monkeypatch.setattr(factory, "_build_llm", lambda provider, model, api_key=None: FakeModel(f"{provider}/{model}/{api_key or 'default'}"))
    monkeypatch.setattr(factory, "provider_api_keys", lambda provider: {"gemini": ["first", "second"], "openai": ["third"]}[provider])
    try:
        config["llm"] = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "fallbacks": [{"provider": "openai", "model": "gpt-4.1-mini"}],
        }
        assert factory.get_llm() == {
            "primary": "gemini/gemini-2.5-flash/first",
            "fallbacks": ["gemini/gemini-2.5-flash/second", "openai/gpt-4.1-mini/third"],
        }
    finally:
        config.clear()
        config.update(original)
