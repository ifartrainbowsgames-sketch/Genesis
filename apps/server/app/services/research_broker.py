from __future__ import annotations

import math
import re
from urllib.parse import urlparse

import httpx

from ..config import settings
from ..schemas import ResearchSource


class ResearchBrokerError(RuntimeError):
    pass


def _configured_base_url() -> str:
    raw = (settings.searxng_url or "").strip().rstrip("/")
    if not raw:
        raise ResearchBrokerError("Research is not configured. Set SEARXNG_URL or start the bundled SearXNG service.")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ResearchBrokerError("SEARXNG_URL must be an http(s) URL")
    if parsed.username or parsed.password:
        raise ResearchBrokerError("SEARXNG_URL must not contain embedded credentials")
    return raw


def _clean(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _score(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


async def search_sources(
    query: str,
    *,
    max_results: int = 8,
    language: str = "all",
    time_range: str | None = None,
    safesearch: int = 1,
) -> list[ResearchSource]:
    query = query.strip()
    if not query:
        raise ResearchBrokerError("Research query cannot be empty")

    max_results = max(1, min(max_results, settings.research_max_results))
    safesearch = max(0, min(safesearch, 2))
    params: dict[str, str] = {
        "q": query,
        "format": "json",
        "pageno": "1",
        "safesearch": str(safesearch),
    }
    if language and language != "all":
        params["language"] = language
    if time_range in {"day", "month", "year"}:
        params["time_range"] = time_range

    endpoint = f"{_configured_base_url()}/search"
    timeout = httpx.Timeout(settings.research_timeout_seconds)
    headers = {"User-Agent": "Genesis-Research/0.1"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ResearchBrokerError(f"SearXNG search failed: {exc}") from exc

    raw_results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw_results, list):
        raise ResearchBrokerError("SearXNG returned an unexpected response")

    sources: list[ResearchSource] = []
    seen: set[str] = set()
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = _clean(item.get("url"), 4000)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen:
            continue
        seen.add(url)

        title = _clean(item.get("title"), 500) or parsed.netloc
        snippet = _clean(item.get("content") or item.get("snippet"), 4000)
        engine_value = item.get("engine") or item.get("engines")
        if isinstance(engine_value, list):
            engine = ", ".join(_clean(value, 80) for value in engine_value[:4])
        else:
            engine = _clean(engine_value, 200) or None

        sources.append(
            ResearchSource(
                id=f"S{len(sources) + 1}",
                title=title,
                url=url,
                snippet=snippet,
                engine=engine,
                score=_score(item.get("score")),
            )
        )
        if len(sources) >= max_results:
            break

    return sources
