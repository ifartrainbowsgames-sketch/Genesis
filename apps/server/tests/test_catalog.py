from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from apps.server.app.schemas import CatalogManifest
from apps.server.app.services import catalog


def _manifest(**overrides: Any) -> CatalogManifest:
    base = dict(
        app_id="windows-terminal",
        name="Windows Terminal",
        category="terminal",
        version="1.21.0",
        platform=["windows"],
        install_type="winget",
        source={"winget_id": "Microsoft.WindowsTerminal"},
        launch_command=["wt"],
        uninstall_command=None,
        license_tier="bundle",
        license_note="MIT",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return CatalogManifest.model_validate(base)


def test_manifest_hash_is_stable_for_identical_manifests() -> None:
    a = _manifest()
    b = _manifest()
    assert catalog.compute_manifest_hash(a) == catalog.compute_manifest_hash(b)


def test_manifest_hash_changes_when_manifest_changes() -> None:
    a = _manifest()
    b = _manifest(version="1.22.0")
    assert catalog.compute_manifest_hash(a) != catalog.compute_manifest_hash(b)


def test_freshness_rejects_recently_published_entries() -> None:
    manifest = _manifest(published_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert catalog.freshness_ok(manifest) is False


def test_freshness_allows_aged_entries() -> None:
    manifest = _manifest(published_at=datetime.now(timezone.utc) - timedelta(hours=200))
    assert catalog.freshness_ok(manifest) is True


def test_install_rejects_stale_manifest_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(catalog, "get_manifest", lambda app_id: manifest)
    with pytest.raises(ValueError, match="changed since approval"):
        asyncio.run(catalog.install_app(app_id="windows-terminal", manifest_hash="stale-hash"))


def test_install_rejects_when_freshness_delay_not_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest(published_at=datetime.now(timezone.utc))
    monkeypatch.setattr(catalog, "get_manifest", lambda app_id: manifest)
    correct_hash = catalog.compute_manifest_hash(manifest)
    with pytest.raises(ValueError, match="freshness delay"):
        asyncio.run(catalog.install_app(app_id="windows-terminal", manifest_hash=correct_hash))


def test_install_uses_fixed_winget_argv_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(catalog, "get_manifest", lambda app_id: manifest)
    monkeypatch.setattr(catalog, "_record_transaction", lambda *a, **k: _noop())
    monkeypatch.setattr(catalog, "_upsert_installation", lambda *a, **k: _noop())
    calls: list[tuple[str, ...]] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"Successfully installed", b""

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        assert "shell" not in kwargs
        return FakeProcess()

    monkeypatch.setattr(catalog.asyncio, "create_subprocess_exec", fake_exec)
    correct_hash = catalog.compute_manifest_hash(manifest)
    result = asyncio.run(catalog.install_app(app_id="windows-terminal", manifest_hash=correct_hash))

    assert calls == [
        (
            "winget", "install", "--exact", "--id", "Microsoft.WindowsTerminal",
            "--silent", "--accept-package-agreements", "--accept-source-agreements", "--scope", "user",
        )
    ]
    assert result["status"] == "installed"


def test_install_uses_fixed_ollama_pull_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest(
        app_id="ollama-qwen3-8b",
        install_type="ollama_pull",
        source={"model": "qwen3:8b"},
        launch_command=None,
    )
    monkeypatch.setattr(catalog, "get_manifest", lambda app_id: manifest)
    monkeypatch.setattr(catalog, "_record_transaction", lambda *a, **k: _noop())
    monkeypatch.setattr(catalog, "_upsert_installation", lambda *a, **k: _noop())
    calls: list[tuple[str, ...]] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"success", b""

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return FakeProcess()

    monkeypatch.setattr(catalog.asyncio, "create_subprocess_exec", fake_exec)
    correct_hash = catalog.compute_manifest_hash(manifest)
    result = asyncio.run(catalog.install_app(app_id="ollama-qwen3-8b", manifest_hash=correct_hash))

    assert calls == [("ollama", "pull", "qwen3:8b")]
    assert result["status"] == "installed"


def test_install_failure_is_rolled_back(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(catalog, "get_manifest", lambda app_id: manifest)
    transactions: list[str] = []

    async def fake_record(app_id: str, phase: str, detail: dict) -> None:
        transactions.append(phase)

    monkeypatch.setattr(catalog, "_record_transaction", fake_record)
    monkeypatch.setattr(catalog, "_upsert_installation", lambda *a, **k: _noop())

    class FakeProcess:
        returncode = 1

        async def communicate(self):
            return b"", b"failed"

    async def fake_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(catalog.asyncio, "create_subprocess_exec", fake_exec)
    correct_hash = catalog.compute_manifest_hash(manifest)
    with pytest.raises(RuntimeError, match="Install failed"):
        asyncio.run(catalog.install_app(app_id="windows-terminal", manifest_hash=correct_hash))
    assert transactions == ["stage", "rollback"]


def test_launch_rejects_stale_manifest_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(catalog, "get_manifest", lambda app_id: manifest)
    with pytest.raises(ValueError, match="changed since approval"):
        asyncio.run(catalog.launch_app(app_id="windows-terminal", manifest_hash="stale-hash"))


def test_launch_requires_executable_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(catalog, "get_manifest", lambda app_id: manifest)
    monkeypatch.setattr(catalog.shutil, "which", lambda _: None)
    correct_hash = catalog.compute_manifest_hash(manifest)
    with pytest.raises(RuntimeError, match="not found on PATH"):
        asyncio.run(catalog.launch_app(app_id="windows-terminal", manifest_hash=correct_hash))


def test_launch_rejects_entries_without_launch_command(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest(launch_command=None)
    monkeypatch.setattr(catalog, "get_manifest", lambda app_id: manifest)
    correct_hash = catalog.compute_manifest_hash(manifest)
    with pytest.raises(ValueError, match="no launch command"):
        asyncio.run(catalog.launch_app(app_id="windows-terminal", manifest_hash=correct_hash))


def test_seed_catalog_index_loads_and_validates() -> None:
    manifests = catalog.load_manifests()
    assert "windows-terminal" in manifests
    assert "ollama-qwen3-8b" in manifests
    for manifest in manifests.values():
        assert manifest.install_type in {"winget", "ollama_pull"}


async def _noop(*args: Any, **kwargs: Any) -> None:
    return None
