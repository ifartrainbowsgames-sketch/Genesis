from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from apps.server.app import desktop_storage
from apps.server.app.schema import CURRENT_SCHEMA_VERSION


def _make_database(path: Path, *, version: int = CURRENT_SCHEMA_VERSION, value: str = "original") -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE genesis_schema_version (
                singleton INTEGER PRIMARY KEY,
                version INTEGER NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO genesis_schema_version (singleton, version) VALUES (1, ?)",
            (version,),
        )
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample (value) VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def test_backup_is_consistent_and_restore_is_staged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "genesis.db"
    _make_database(database)
    monkeypatch.setattr(desktop_storage, "_database_path", lambda: database)

    backup = desktop_storage.create_backup()
    assert backup["name"].startswith("genesis-backup-")
    assert backup["schemaVersion"] == CURRENT_SCHEMA_VERSION
    assert backup["bytes"] > 0

    backup_path = tmp_path / "backups" / backup["name"]
    restored = sqlite3.connect(backup_path)
    try:
        assert restored.execute("SELECT value FROM sample").fetchone()[0] == "original"
    finally:
        restored.close()

    listed = desktop_storage.list_backups()
    assert [item["name"] for item in listed] == [backup["name"]]

    staged = desktop_storage.stage_restore(backup["name"])
    assert staged["staged"] is True
    assert staged["restartRequired"] is True
    assert (tmp_path / desktop_storage.PENDING_RESTORE).is_file()


def test_restore_rejects_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "genesis.db"
    _make_database(database)
    monkeypatch.setattr(desktop_storage, "_database_path", lambda: database)

    with pytest.raises(ValueError, match="Invalid Genesis backup name"):
        desktop_storage.stage_restore("../genesis-backup-evil.db")


def test_restore_rejects_database_from_newer_genesis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "genesis.db"
    _make_database(database)
    monkeypatch.setattr(desktop_storage, "_database_path", lambda: database)

    backups = tmp_path / "backups"
    backups.mkdir()
    future = backups / "genesis-backup-future.db"
    _make_database(future, version=CURRENT_SCHEMA_VERSION + 1, value="future")

    with pytest.raises(ValueError, match="newer than this Genesis build"):
        desktop_storage.stage_restore(future.name)
    assert not (tmp_path / desktop_storage.PENDING_RESTORE).exists()


def test_corrupt_backup_is_not_offered_for_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "genesis.db"
    _make_database(database)
    monkeypatch.setattr(desktop_storage, "_database_path", lambda: database)

    backups = tmp_path / "backups"
    backups.mkdir()
    corrupt = backups / "genesis-backup-corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")

    assert desktop_storage.list_backups() == []
    with pytest.raises(sqlite3.DatabaseError):
        desktop_storage.stage_restore(corrupt.name)
