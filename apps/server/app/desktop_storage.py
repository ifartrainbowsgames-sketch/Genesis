from __future__ import annotations

import asyncio
import shutil
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from starlette.responses import JSONResponse

from .db import database_backend, engine
from .schema import CURRENT_SCHEMA_VERSION


ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]]
BACKUP_PREFIXES = ("genesis-backup-", "genesis-pre-restore-")
PENDING_RESTORE = "restore.pending.db"


def _database_path() -> Path:
    if database_backend() != "sqlite" or not engine.url.database:
        raise RuntimeError("Desktop backup/restore is available only with the embedded SQLite database")
    return Path(str(engine.url.database)).expanduser().resolve()


def _backup_dir(database_path: Path) -> Path:
    path = database_path.parent / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_backup_path(database_path: Path, name: str) -> Path:
    if not name or Path(name).name != name or not name.endswith(".db") or not name.startswith(BACKUP_PREFIXES):
        raise ValueError("Invalid Genesis backup name")
    candidate = (_backup_dir(database_path) / name).resolve()
    if candidate.parent != _backup_dir(database_path).resolve():
        raise ValueError("Backup path escapes the Genesis backup directory")
    if not candidate.is_file():
        raise FileNotFoundError(name)
    return candidate


def _validate_backup(path: Path) -> int:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        if not quick_check or str(quick_check[0]).lower() != "ok":
            raise ValueError("SQLite integrity check failed")
        row = connection.execute(
            "SELECT version FROM genesis_schema_version WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise ValueError("Backup does not contain Genesis schema version metadata")
        version = int(row[0])
        if version < 1:
            raise ValueError("Backup has an invalid Genesis schema version")
        if version > CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"Backup schema {version} is newer than this Genesis build ({CURRENT_SCHEMA_VERSION})"
            )
        return version
    finally:
        connection.close()


def _backup_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "bytes": stat.st_size,
        "schemaVersion": _validate_backup(path),
        "modifiedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def list_backups() -> list[dict[str, Any]]:
    database_path = _database_path()
    backups: list[dict[str, Any]] = []
    for path in sorted(_backup_dir(database_path).glob("*.db"), reverse=True):
        if not path.name.startswith(BACKUP_PREFIXES):
            continue
        try:
            backups.append(_backup_info(path))
        except (OSError, sqlite3.Error, ValueError):
            # Invalid/corrupt files are never offered as restore candidates.
            continue
    return backups


def create_backup() -> dict[str, Any]:
    database_path = _database_path()
    if not database_path.is_file():
        raise FileNotFoundError("Genesis embedded database does not exist yet")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = _backup_dir(database_path) / f"genesis-backup-{timestamp}.db"

    source = sqlite3.connect(str(database_path), timeout=10)
    target = sqlite3.connect(str(destination), timeout=10)
    try:
        source.backup(target, pages=128, sleep=0.01)
    except Exception:
        target.close()
        source.close()
        destination.unlink(missing_ok=True)
        raise
    else:
        target.close()
        source.close()

    return _backup_info(destination)


def stage_restore(name: str) -> dict[str, Any]:
    database_path = _database_path()
    source = _safe_backup_path(database_path, name)
    schema_version = _validate_backup(source)
    pending = database_path.parent / PENDING_RESTORE
    temporary = database_path.parent / f"{PENDING_RESTORE}.tmp"
    temporary.unlink(missing_ok=True)
    shutil.copy2(source, temporary)
    temporary.replace(pending)
    return {
        "staged": True,
        "name": source.name,
        "schemaVersion": schema_version,
        "restartRequired": True,
    }


def _cors_headers(scope: dict[str, Any], web_origin: str) -> dict[str, str]:
    headers = {key.lower(): value for key, value in scope.get("headers", [])}
    origin = headers.get(b"origin", b"").decode("utf-8", errors="ignore")
    if origin == web_origin:
        return {
            "access-control-allow-origin": origin,
            "access-control-allow-credentials": "true",
            "vary": "Origin",
            "cache-control": "no-store",
        }
    return {"cache-control": "no-store"}


class DesktopStorageMiddleware:
    """Desktop-only backup API wrapped by the per-launch token middleware."""

    def __init__(self, app: ASGIApp, web_origin: str) -> None:
        self.app = app
        self.web_origin = web_origin

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        try:
            if path == "/v1/system/backups" and method == "GET":
                payload = await asyncio.to_thread(list_backups)
                response = JSONResponse(
                    {"backups": payload},
                    headers=_cors_headers(scope, self.web_origin),
                )
                await response(scope, receive, send)
                return

            if path == "/v1/system/backups" and method == "POST":
                payload = await asyncio.to_thread(create_backup)
                response = JSONResponse(
                    payload,
                    status_code=201,
                    headers=_cors_headers(scope, self.web_origin),
                )
                await response(scope, receive, send)
                return

            prefix = "/v1/system/backups/"
            suffix = "/restore"
            if path.startswith(prefix) and path.endswith(suffix) and method == "POST":
                name = unquote(path[len(prefix) : -len(suffix)])
                payload = await asyncio.to_thread(stage_restore, name)
                response = JSONResponse(
                    payload,
                    headers=_cors_headers(scope, self.web_origin),
                )
                await response(scope, receive, send)
                return
        except FileNotFoundError as exc:
            response = JSONResponse(
                {"detail": str(exc)},
                status_code=404,
                headers=_cors_headers(scope, self.web_origin),
            )
            await response(scope, receive, send)
            return
        except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
            response = JSONResponse(
                {"detail": str(exc)},
                status_code=400,
                headers=_cors_headers(scope, self.web_origin),
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
