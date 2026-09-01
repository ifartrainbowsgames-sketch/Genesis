from __future__ import annotations

import pytest

from apps.server.app.services import mcp_registry


def test_registry_accepts_only_enabled_http_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_registry.settings,
        "mcp_servers_json",
        '[{"name":"local-tools","url":"http://127.0.0.1:9000/mcp","enabled":true},'
        '{"name":"disabled","url":"https://example.test/mcp","enabled":false}]',
    )

    servers = mcp_registry.list_servers()

    assert [(server.name, server.url) for server in servers] == [
        ("local-tools", "http://127.0.0.1:9000/mcp")
    ]
    with pytest.raises(KeyError, match="Unknown or disabled MCP server"):
        mcp_registry.require_server("disabled")


def test_registry_rejects_embedded_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_registry.settings,
        "mcp_servers_json",
        '[{"name":"unsafe","url":"https://user:pass@example.test/mcp"}]',
    )

    with pytest.raises(ValueError, match="must not embed credentials"):
        mcp_registry.list_servers()


def test_registry_rejects_non_http_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_registry.settings,
        "mcp_servers_json",
        '[{"name":"stdio","url":"file:///tmp/server"}]',
    )

    with pytest.raises(ValueError, match=r"explicit http\(s\) URL"):
        mcp_registry.list_servers()


def test_registry_rejects_duplicate_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_registry.settings,
        "mcp_servers_json",
        '[{"name":"same","url":"http://one.test/mcp"},'
        '{"name":"same","url":"http://two.test/mcp"}]',
    )

    with pytest.raises(ValueError, match="Duplicate MCP server name"):
        mcp_registry.list_servers()
