"""Workspace-scoped MCP connection settings and safe public metadata."""

from __future__ import annotations

from copy import deepcopy
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = Path(__file__).parent / "mcp_servers_config.json"
_WORKSPACE_CONFIG_NAME = "mcp_servers.json"
_SERVER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

# Prepend common Node.js binary locations (nvm, Homebrew, system) so stdio MCP
# subprocesses can find `node` even when the app was not started from a shell.
_NODE_BIN_DIRS = [
    str(Path.home() / ".nvm/versions/node/v24.21.0/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
]
_INJECTED_PATH = ":".join(_NODE_BIN_DIRS + [os.environ.get("PATH", "")])

PRESET_DETAILS = {
    "filesystem": {
        "label": "Filesystem",
        "description": "Lets the agent inspect files in the workspace through MCP.",
        "requires": "Node.js 18+",
    },
    "github": {
        "label": "GitHub",
        "description": "Lets the agent work with GitHub when you explicitly request remote work.",
        "requires": "Node.js 18+ and GITHUB_TOKEN",
    },
}


def _workspace_config_path() -> Path:
    return Path.cwd() / ".claude_code" / _WORKSPACE_CONFIG_NAME


def _default_servers() -> dict[str, dict[str, Any]]:
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return raw.get("mcp_servers", {})


def _workspace_servers() -> dict[str, dict[str, Any]]:
    """Read locally persisted MCP connections; malformed files fail closed."""
    path = _workspace_config_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    servers = raw.get("mcp_servers", {}) if isinstance(raw, dict) else {}
    return servers if isinstance(servers, dict) else {}


def _write_workspace_servers(servers: dict[str, dict[str, Any]]) -> None:
    path = _workspace_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mcp_servers": servers}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_server(server: dict[str, Any]) -> dict[str, Any]:
    """Expand env placeholders only while building the process configuration."""
    serialized = json.dumps(server)
    resolved = re.sub(r"\$\{(\w+)\}", lambda match: os.getenv(match.group(1), ""), serialized)
    result = json.loads(resolved)
    environment = result.setdefault("env", {})
    environment.setdefault("PATH", _INJECTED_PATH)
    return result


def _legacy_opt_in_servers() -> dict[str, dict[str, Any]]:
    """Preserve the original environment-variable activation path."""
    if os.getenv("CLAUDE_CODE_ENABLE_MCP", "").lower() not in {"1", "true", "yes"}:
        return {}
    servers = _default_servers()
    if os.getenv("CLAUDE_CODE_ENABLE_GITHUB_MCP", "").lower() not in {"1", "true", "yes"}:
        servers.pop("github", None)
    return servers


def load_mcp_configs() -> dict:
    """Return configured MCP servers for the current workspace.

    Connections saved in `.claude_code/mcp_servers.json` are local-only and
    become available on the next agent request. The prior environment-variable
    opt-in continues to work for terminal-only users.
    """
    os.environ.setdefault("CWD", str(Path.cwd()))
    servers = _legacy_opt_in_servers()
    servers.update(_workspace_servers())
    return {name: _resolve_server(server) for name, server in servers.items() if isinstance(server, dict)}


def _public_server(name: str, server: dict[str, Any], origin: str) -> dict[str, Any]:
    preset = PRESET_DETAILS.get(name, {})
    environment = server.get("env", {})
    return {
        "name": name,
        "label": preset.get("label", name.replace("-", " ").replace("_", " ").title()),
        "description": preset.get("description", "Custom workspace MCP server."),
        "requires": preset.get("requires", "Command available on this computer"),
        "command": str(server.get("command", "")),
        "args": [str(item) for item in server.get("args", [])],
        "env_keys": sorted(str(key) for key in environment) if isinstance(environment, dict) else [],
        "transport": str(server.get("transport", "stdio")),
        "origin": origin,
    }


def public_mcp_servers() -> list[dict[str, Any]]:
    """List available and configured connections without exposing env values."""
    defaults = _default_servers()
    workspace = _workspace_servers()
    legacy = _legacy_opt_in_servers()
    result = []
    for name in PRESET_DETAILS:
        server = workspace.get(name) or legacy.get(name) or defaults[name]
        result.append({**_public_server(name, server, "preset"), "enabled": name in workspace or name in legacy})
    for name, server in workspace.items():
        if name not in PRESET_DETAILS and isinstance(server, dict):
            result.append({**_public_server(name, server, "custom"), "enabled": True})
    return result


def set_preset_enabled(name: str, enabled: bool) -> list[dict[str, Any]]:
    """Enable or remove a built-in local MCP connection for this workspace."""
    if name not in PRESET_DETAILS:
        raise ValueError(f"Unknown MCP preset: {name}")
    servers = _workspace_servers()
    if enabled:
        servers[name] = deepcopy(_default_servers()[name])
    else:
        servers.pop(name, None)
    _write_workspace_servers(servers)
    return public_mcp_servers()


def save_custom_mcp_server(
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Save a stdio MCP process definition locally after basic validation."""
    normalized_name = name.strip()
    normalized_command = command.strip()
    if not _SERVER_NAME.fullmatch(normalized_name):
        raise ValueError("Use 1–64 letters, numbers, dots, dashes, or underscores for the server name")
    if normalized_name in PRESET_DETAILS:
        raise ValueError("Use the preset toggle for built-in MCP servers")
    if not normalized_command:
        raise ValueError("A command is required")
    cleaned_args = [str(item).strip() for item in args or [] if str(item).strip()]
    cleaned_env = {str(key).strip(): str(value) for key, value in (env or {}).items() if str(key).strip()}
    servers = _workspace_servers()
    servers[normalized_name] = {
        "command": normalized_command,
        "args": cleaned_args,
        "env": cleaned_env,
        "transport": "stdio",
    }
    _write_workspace_servers(servers)
    return public_mcp_servers()


def remove_custom_mcp_server(name: str) -> list[dict[str, Any]]:
    """Remove a custom connection; presets must be disabled through their toggle."""
    if name in PRESET_DETAILS:
        return set_preset_enabled(name, False)
    servers = _workspace_servers()
    if name not in servers:
        raise ValueError(f"Unknown MCP server: {name}")
    servers.pop(name)
    _write_workspace_servers(servers)
    return public_mcp_servers()
