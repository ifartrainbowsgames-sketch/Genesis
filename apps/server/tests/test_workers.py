from __future__ import annotations

import asyncio

import pytest

from apps.server.app.schemas import WorkerRunRequest
from apps.server.app.services import workers


def test_workers_always_include_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workers.settings, "external_workers_json", "[]")
    result = workers.list_workers()
    assert result[0].name == "genesis-team"
    assert result[0].type == "builtin"


def test_command_worker_requires_fixed_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workers.settings,
        "external_workers_json",
        '[{"name":"bad","type":"command","argv":[],"enabled":true}]',
    )
    with pytest.raises(ValueError, match="argv"):
        workers.list_workers()


def test_http_worker_rejects_non_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workers.settings,
        "external_workers_json",
        '[{"name":"bad","type":"http","url":"file:///tmp/worker","enabled":true}]',
    )
    with pytest.raises(ValueError, match="http"):
        workers.list_workers()


def test_command_worker_uses_exec_not_shell(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(workers.workspace_manager, "_selected", tmp_path)
    monkeypatch.setattr(
        workers.settings,
        "external_workers_json",
        '[{"name":"echo-worker","type":"command","argv":["fixed-tool","--mode","safe"],"enabled":true}]',
    )
    calls: list[tuple[str, ...]] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self, payload: bytes):
            assert payload == b"hello"
            return b"ok", b""

        def kill(self) -> None:
            pass

        async def wait(self) -> None:
            pass

    async def fake_exec(*args, **kwargs):
        calls.append(tuple(args))
        assert kwargs["cwd"] == tmp_path
        assert "shell" not in kwargs
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = asyncio.run(workers.run_worker(WorkerRunRequest(worker="echo-worker", prompt="hello")))
    assert calls == [("fixed-tool", "--mode", "safe")]
    assert result.output == "ok"
