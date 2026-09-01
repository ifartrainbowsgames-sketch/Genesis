from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse

from ..config import settings


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    url: str
    enabled: bool = True


def _load() -> dict[str, MCPServerConfig]:
    raw = settings.mcp_servers_json.strip() or "[]"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MCP_SERVERS_JSON must be valid JSON") from exc
    if not isinstance(data, list):
        raise ValueError("MCP_SERVERS_JSON must be a JSON array")

    servers: dict[str, MCPServerConfig] = {}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Every MCP server entry must be an object")
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        enabled = bool(item.get("enabled", True))
        if not name or len(name) > 80 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for ch in name):
            raise ValueError(f"Invalid MCP server name: {name!r}")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(f"MCP server {name!r} must use an explicit http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError(f"MCP server {name!r} must not embed credentials in its URL")
        if name in servers:
            raise ValueError(f"Duplicate MCP server name: {name}")
        servers[name] = MCPServerConfig(name=name, url=url, enabled=enabled)
    return servers


def list_servers() -> list[MCPServerConfig]:
    return [server for server in _load().values() if server.enabled]


def require_server(name: str) -> MCPServerConfig:
    server = _load().get(name)
    if not server or not server.enabled:
        raise KeyError(f"Unknown or disabled MCP server: {name}")
    return server
