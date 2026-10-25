from claude_code.mcp.mcp_config import (
    load_mcp_configs,
    public_mcp_servers,
    save_custom_mcp_server,
    set_preset_enabled,
)


def test_mcp_is_disabled_without_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_ENABLE_MCP", raising=False)

    assert load_mcp_configs() == {}


def test_mcp_opt_in_excludes_github_by_default(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_ENABLE_MCP", "true")
    monkeypatch.delenv("CLAUDE_CODE_ENABLE_GITHUB_MCP", raising=False)

    assert set(load_mcp_configs()) == {"filesystem"}


def test_custom_workspace_mcp_loads_without_legacy_opt_in(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_ENABLE_MCP", raising=False)
    save_custom_mcp_server(
        "example",
        "npx",
        ["-y", "example-mcp"],
        {"EXAMPLE_TOKEN": "local-secret"},
    )

    configs = load_mcp_configs()

    assert configs["example"]["command"] == "npx"
    assert configs["example"]["args"] == ["-y", "example-mcp"]
    assert configs["example"]["env"]["EXAMPLE_TOKEN"] == "local-secret"
    assert "PATH" in configs["example"]["env"]


def test_mcp_catalog_redacts_custom_environment_values(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    save_custom_mcp_server("safe-name", "node", ["server.js"], {"TOKEN": "never-show-this"})

    catalog = public_mcp_servers()
    custom = next(server for server in catalog if server["name"] == "safe-name")

    assert custom["enabled"] is True
    assert custom["env_keys"] == ["TOKEN"]
    assert "never-show-this" not in str(catalog)


def test_preset_toggle_persists_workspace_connection(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    catalog = set_preset_enabled("filesystem", True)

    filesystem = next(server for server in catalog if server["name"] == "filesystem")
    assert filesystem["enabled"] is True
    assert set(load_mcp_configs()) == {"filesystem"}
