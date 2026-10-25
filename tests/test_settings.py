from copy import deepcopy
import os
from pathlib import Path

from claude_code.config import config
from claude_code.llm import factory
from claude_code.settings import save_llm_settings


def test_settings_save_key_locally_without_returning_it(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("llm:\n  provider: gemini\n  model: old\n", encoding="utf-8")
    original = deepcopy(config)
    original_key = os.getenv("OPENAI_API_KEY")
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
        assert "provider: openai" in (tmp_path / "config.yaml").read_text(encoding="utf-8")
    finally:
        config.clear()
        config.update(original)
        if original_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = original_key


def test_llm_factory_wraps_configured_fallbacks(monkeypatch) -> None:
    class FakeModel:
        def __init__(self, name: str) -> None:
            self.name = name

        def with_fallbacks(self, fallbacks):
            return {"primary": self.name, "fallbacks": [fallback.name for fallback in fallbacks]}

    original = deepcopy(config)
    monkeypatch.setattr(factory, "_build_llm", lambda provider, model: FakeModel(f"{provider}/{model}"))
    try:
        config["llm"] = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "fallbacks": [{"provider": "openai", "model": "gpt-4.1-mini"}],
        }
        assert factory.get_llm() == {
            "primary": "gemini/gemini-2.5-flash",
            "fallbacks": ["openai/gpt-4.1-mini"],
        }
    finally:
        config.clear()
        config.update(original)
