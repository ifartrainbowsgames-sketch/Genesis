from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from apps.server.app.services import memory


@dataclass
class FakeResponse:
    payload: dict[str, Any]
    is_success: bool = True

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeAsyncClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
        self.calls.append((url, json))
        return self.responses.pop(0)


def test_embed_text_uses_primary_ollama_embed_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory.settings, "embedding_dim", 3)
    monkeypatch.setattr(memory.settings, "ollama_base_url", "http://ollama.test/")
    client = FakeAsyncClient([FakeResponse({"embeddings": [[0.1, 0.2, 0.3]]})])
    monkeypatch.setattr(memory.httpx, "AsyncClient", lambda **_: client)

    vector = asyncio.run(memory.embed_text("hello"))

    assert vector == [0.1, 0.2, 0.3]
    assert client.calls == [
        (
            "http://ollama.test/api/embed",
            {
                "model": memory.settings.ollama_embed_model,
                "input": "hello",
                "dimensions": 3,
            },
        )
    ]


def test_embed_text_falls_back_to_legacy_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory.settings, "embedding_dim", 3)
    client = FakeAsyncClient(
        [
            FakeResponse({"embeddings": [[0.1, 0.2]]}),
            FakeResponse({"embedding": [0.4, 0.5, 0.6]}),
        ]
    )
    monkeypatch.setattr(memory.httpx, "AsyncClient", lambda **_: client)

    vector = asyncio.run(memory.embed_text("fallback"))

    assert vector == [0.4, 0.5, 0.6]
    assert client.calls[0][0].endswith("/api/embed")
    assert client.calls[1][0].endswith("/api/embeddings")


def test_embed_text_rejects_wrong_dimension_from_both_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(memory.settings, "embedding_dim", 3)
    client = FakeAsyncClient(
        [
            FakeResponse({"embeddings": [[0.1, 0.2]]}),
            FakeResponse({"embedding": [0.4, 0.5]}),
        ]
    )
    monkeypatch.setattr(memory.httpx, "AsyncClient", lambda **_: client)

    assert asyncio.run(memory.embed_text("bad dimensions")) is None


def test_delete_memory_rejects_invalid_uuid_before_database_access() -> None:
    with pytest.raises(ValueError, match="Invalid memory id"):
        asyncio.run(memory.delete_memory("not-a-uuid"))
