from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import text

from ..config import settings
from ..db import SessionLocal
from .mcp_registry import list_servers


def _component(status: str, detail: str, **extra) -> dict:
    return {"status": status, "detail": detail, **extra}


async def _database() -> dict:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return _component("ready", "PostgreSQL connection succeeded")
    except Exception as exc:
        return _component("unavailable", f"PostgreSQL unavailable: {type(exc).__name__}")


async def _ollama() -> dict:
    base = settings.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base}/api/tags")
            response.raise_for_status()
            payload = response.json()
        model_count = len(payload.get("models", [])) if isinstance(payload, dict) else 0
        return _component("ready", f"Ollama responded with {model_count} installed model(s)", models=model_count)
    except Exception as exc:
        return _component("unavailable", f"Ollama unavailable: {type(exc).__name__}")


async def _searxng() -> dict:
    if not settings.searxng_url:
        return _component("not_configured", "SEARXNG_URL is not configured")
    parsed = urlparse(settings.searxng_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _component("invalid", "SEARXNG_URL is invalid")
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            response = await client.get(settings.searxng_url.rstrip("/") + "/")
            response.raise_for_status()
        return _component("ready", "SearXNG responded")
    except Exception as exc:
        return _component("unavailable", f"SearXNG unavailable: {type(exc).__name__}")


def _voice() -> dict:
    if not settings.whisper_cpp_binary or not settings.whisper_cpp_model:
        return _component("not_configured", "Set WHISPER_CPP_BINARY and WHISPER_CPP_MODEL to enable local STT")
    binary_ok = Path(settings.whisper_cpp_binary).expanduser().is_file()
    model_ok = Path(settings.whisper_cpp_model).expanduser().is_file()
    if binary_ok and model_ok:
        return _component("ready", "whisper.cpp executable and model are present")
    missing = []
    if not binary_ok:
        missing.append("binary")
    if not model_ok:
        missing.append("model")
    return _component("unavailable", "Missing whisper.cpp " + " and ".join(missing))


def _github() -> dict:
    if settings.github_token:
        return _component("configured", "GitHub token is configured server-side")
    return _component("not_configured", "GITHUB_TOKEN is not configured")


def _mcp() -> dict:
    try:
        servers = list_servers()
        return _component("configured" if servers else "not_configured", f"{len(servers)} enabled MCP server(s)", servers=len(servers))
    except Exception as exc:
        return _component("invalid", f"MCP configuration error: {exc}")


async def system_health() -> dict:
    database, ollama, searxng = await asyncio.gather(_database(), _ollama(), _searxng())
    components = {
        "database": database,
        "ollama": ollama,
        "research": searxng,
        "voice": _voice(),
        "github": _github(),
        "mcp": _mcp(),
    }
    essential_ready = all(components[name]["status"] == "ready" for name in ("database", "ollama"))
    return {
        "status": "ready" if essential_ready else "degraded",
        "components": components,
    }
