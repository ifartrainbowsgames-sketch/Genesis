from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from apps.server.app.services import research_broker


@dataclass
class FakeResponse:
    payload: dict[str, Any]

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeAsyncClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.endpoint: str | None = None
        self.params: dict[str, str] | None = None

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, endpoint: str, params: dict[str, str]) -> FakeResponse:
        self.endpoint = endpoint
        self.params = params
        return self.response


def test_configured_base_url_rejects_embedded_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        research_broker.settings, "searxng_url", "https://user:pass@search.example.test"
    )

    with pytest.raises(research_broker.ResearchBrokerError, match="embedded credentials"):
        research_broker._configured_base_url()


def test_search_sources_filters_invalid_and_duplicate_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(research_broker.settings, "searxng_url", "http://127.0.0.1:8080/")
    monkeypatch.setattr(research_broker.settings, "research_max_results", 5)
    response = FakeResponse(
        {
            "results": [
                {"url": "javascript:alert(1)", "title": "bad"},
                {
                    "url": "https://example.test/a",
                    "title": "  First   result  ",
                    "content": " useful   snippet ",
                    "engine": "engine-a",
                    "score": 1.5,
                },
                {"url": "https://example.test/a", "title": "duplicate"},
                {
                    "url": "https://second.test/b",
                    "title": "",
                    "snippet": "second",
                    "engines": ["one", "two"],
                    "score": "inf",
                },
            ]
        }
    )
    client = FakeAsyncClient(response)
    monkeypatch.setattr(research_broker.httpx, "AsyncClient", lambda **_: client)

    sources = asyncio.run(
        research_broker.search_sources(
            " genesis testing ", max_results=5, language="en", time_range="month", safesearch=99
        )
    )

    assert client.endpoint == "http://127.0.0.1:8080/search"
    assert client.params == {
        "q": "genesis testing",
        "format": "json",
        "pageno": "1",
        "safesearch": "2",
        "language": "en",
        "time_range": "month",
    }
    assert [source.id for source in sources] == ["S1", "S2"]
    assert sources[0].title == "First result"
    assert sources[0].snippet == "useful snippet"
    assert sources[0].score == 1.5
    assert sources[1].title == "second.test"
    assert sources[1].engine == "one, two"
    assert sources[1].score is None


def test_search_sources_rejects_empty_query() -> None:
    with pytest.raises(research_broker.ResearchBrokerError, match="cannot be empty"):
        asyncio.run(research_broker.search_sources("   "))
