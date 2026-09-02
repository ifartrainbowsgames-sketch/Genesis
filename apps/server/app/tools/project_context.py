from __future__ import annotations

from typing import Any

from ..services.project_context import context_for, search, snapshot


def context_snapshot() -> dict[str, Any]:
    return snapshot()


def context_search(query: str, limit: int = 20) -> dict[str, Any]:
    return {"query": query, "hits": search(query, limit=limit)}


def context_read(query: str, max_files: int = 10, max_total_chars: int = 60_000) -> dict[str, Any]:
    bounded_files = max(1, min(max_files, 16))
    bounded_chars = max(4_000, min(max_total_chars, 80_000))
    content, files = context_for(query, max_files=bounded_files, max_total_chars=bounded_chars)
    return {"query": query, "files": files, "content": content}
