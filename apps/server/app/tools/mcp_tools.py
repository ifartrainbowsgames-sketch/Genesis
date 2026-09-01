from __future__ import annotations

from typing import Any

from mcp import Client

from ..services.mcp_registry import list_servers, require_server


def servers() -> dict[str, Any]:
    return {
        "servers": [
            {"name": item.name, "url": item.url}
            for item in list_servers()
        ]
    }


async def list_tools(server: str) -> dict[str, Any]:
    config = require_server(server)
    async with Client(config.url, mode="auto") as client:
        result = await client.list_tools()
    return {
        "server": config.name,
        "protocol_version": str(client.protocol_version) if client.protocol_version else None,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "annotations": tool.annotations.model_dump(by_alias=True, exclude_none=True) if tool.annotations else None,
            }
            for tool in result.tools
        ],
    }


async def call_tool(server: str, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    config = require_server(server)
    if not name.strip():
        raise ValueError("MCP tool name is required")
    async with Client(config.url, mode="auto") as client:
        listed = await client.list_tools()
        allowed = {tool.name for tool in listed.tools}
        if name not in allowed:
            raise ValueError(f"MCP server {server!r} does not advertise tool {name!r}")
        result = await client.call_tool(name, arguments or {})
    return {
        "server": config.name,
        "tool": name,
        "result": result.model_dump(by_alias=True, exclude_none=True),
    }
