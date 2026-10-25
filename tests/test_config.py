from claude_code.config import DEFAULT_CONFIG, _merge_defaults


def test_merge_defaults_preserves_nested_defaults() -> None:
    config = _merge_defaults(DEFAULT_CONFIG, {"llm": {"provider": "openai"}})

    assert config["llm"] == {
        "provider": "openai",
        "model": "gemini-2.5-flash",
        "fallbacks": [],
    }
    assert config["vectorstore"]["provider"] == "faiss"


def test_merge_defaults_allows_overriding_a_scalar() -> None:
    config = _merge_defaults(DEFAULT_CONFIG, {"memory": {"keep_last_messages": 5}})

    assert config["memory"]["keep_last_messages"] == 5
    assert config["memory"]["db_path"] == ".memory/memory.db"
