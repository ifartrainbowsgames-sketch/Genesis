from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import settings
from ..services.workspace_manager import workspace_manager


SKIP_PARTS = {".git", "node_modules", ".next", ".venv", "venv", "dist", "build", "target", "__pycache__"}
MAX_CHECKPOINTS = 50


def _safe_path(relative_path: str) -> Path:
    root = workspace_manager.path
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path escapes workspace root")
    return candidate


def _visible(relative: Path) -> bool:
    return not any(part in SKIP_PARTS for part in relative.parts)


def _state_root() -> Path:
    configured = os.getenv("GENESIS_STATE_DIR", "").strip()
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        database_url = settings.database_url
        prefix = "sqlite+aiosqlite:///"
        if database_url.startswith(prefix):
            database_path = Path(database_url[len(prefix):]).expanduser().resolve()
            root = database_path.parent / "state"
        else:
            root = Path.home().joinpath(".genesis", "state").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _checkpoint_dir() -> Path:
    path = _state_root() / "checkpoints"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _checkpoint_path(checkpoint_id: str) -> Path:
    try:
        parsed = uuid.UUID(checkpoint_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid checkpoint id") from exc
    return _checkpoint_dir() / f"{parsed}.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_bytes_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.genesis-{uuid.uuid4().hex}.tmp")
    try:
        temp.write_bytes(data)
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def _write_json_atomic(target: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    _write_bytes_atomic(target, encoded)


def _load_checkpoint(checkpoint_id: str) -> tuple[Path, dict[str, Any]]:
    path = _checkpoint_path(checkpoint_id)
    if not path.is_file():
        raise FileNotFoundError("Checkpoint not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Checkpoint is unreadable") from exc
    if payload.get("checkpoint_id") != checkpoint_id:
        raise ValueError("Checkpoint identity mismatch")
    if payload.get("workspace") != str(workspace_manager.path.resolve()):
        raise ValueError("Checkpoint belongs to a different workspace")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Checkpoint has no file snapshots")
    return path, payload


def _restore_snapshot(payload: dict[str, Any], *, verify_applied: bool) -> list[str]:
    files = payload["files"]
    conflicts: list[str] = []
    if verify_applied:
        for item in files:
            path = str(item["path"])
            target = _safe_path(path)
            applied_hash = str(item["applied_sha256"])
            if not target.is_file() or _sha256(target.read_bytes()) != applied_hash:
                conflicts.append(path)
        if conflicts:
            raise ValueError(
                "Undo refused because these files changed after Genesis applied them: "
                + ", ".join(conflicts)
            )

    restored: list[str] = []
    for item in files:
        path = str(item["path"])
        target = _safe_path(path)
        if bool(item["existed"]):
            try:
                original = base64.b64decode(str(item["original_base64"]), validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Checkpoint snapshot is invalid for {path}") from exc
            _write_bytes_atomic(target, original)
        else:
            if target.exists():
                if not target.is_file():
                    raise ValueError(f"Cannot undo created file because path is no longer a file: {path}")
                target.unlink()
        restored.append(path)
    return restored


def _prune_checkpoints() -> None:
    directory = _checkpoint_dir()
    files = sorted(
        (path for path in directory.glob("*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files[MAX_CHECKPOINTS:]:
        path.unlink(missing_ok=True)


def list_files(path: str = ".", recursive: bool = False) -> dict[str, Any]:
    target = _safe_path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    if not target.is_dir():
        raise NotADirectoryError(path)

    iterator = target.rglob("*") if recursive else target.iterdir()
    items = []
    for item in iterator:
        relative = item.relative_to(workspace_manager.path)
        if not _visible(relative):
            continue
        items.append({
            "path": str(relative).replace("\\", "/"),
            "type": "dir" if item.is_dir() else "file",
            "size": item.stat().st_size if item.is_file() else None,
        })
        if len(items) >= 1000:
            break
    return {"items": items}


def read_file(path: str, max_bytes: int = 200_000) -> dict[str, Any]:
    target = _safe_path(path)
    if not target.is_file():
        raise FileNotFoundError(path)
    data = target.read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"File exceeds read limit of {max_bytes} bytes")
    return {"path": path, "content": data.decode("utf-8", errors="replace")}


def write_file(path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    encoded = content.encode("utf-8")
    if len(encoded) > settings.max_file_write_bytes:
        raise ValueError(f"Write exceeds {settings.max_file_write_bytes} byte limit")

    target = _safe_path(path)
    if target.exists() and not overwrite:
        raise FileExistsError("File already exists; set overwrite=true to replace it")
    _write_bytes_atomic(target, encoded)
    return {"path": path, "bytes_written": len(encoded)}


def mkdir(path: str) -> dict[str, Any]:
    target = _safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": path, "created": True}


def checkpoints() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for path in sorted(_checkpoint_dir().glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        if len(items) >= MAX_CHECKPOINTS:
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("workspace") != str(workspace_manager.path.resolve()):
                continue
            files = payload.get("files", [])
            items.append({
                "checkpoint_id": payload.get("checkpoint_id"),
                "created_at": payload.get("created_at"),
                "file_count": len(files) if isinstance(files, list) else 0,
                "paths": [str(item.get("path", "")) for item in files if isinstance(item, dict)][:50],
            })
        except (OSError, json.JSONDecodeError):
            continue
    return {"checkpoints": items}


def apply_changes(changes: list[dict[str, Any]]) -> dict[str, Any]:
    if not changes:
        raise ValueError("No changes supplied")
    if len(changes) > 50:
        raise ValueError("A single change set may contain at most 50 files")

    prepared: list[tuple[Path, bytes, str, str]] = []
    snapshots: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0

    for change in changes:
        path = str(change.get("path", "")).strip().replace("\\", "/")
        action = str(change.get("action", "replace")).strip()
        content = change.get("content")
        if not path or action not in {"create", "replace"} or not isinstance(content, str):
            raise ValueError("Each change requires path, action=create|replace, and string content")
        if path in seen:
            raise ValueError(f"Duplicate change path: {path}")
        seen.add(path)

        target = _safe_path(path)
        encoded = content.encode("utf-8")
        total += len(encoded)
        if total > settings.max_file_write_bytes:
            raise ValueError(f"Change set exceeds {settings.max_file_write_bytes} byte limit")
        if target.exists() and not target.is_file():
            raise ValueError(f"Change target is not a file: {path}")
        if action == "create" and target.exists():
            raise FileExistsError(f"File already exists: {path}")

        original = target.read_bytes() if target.is_file() else b""
        if len(original) > settings.max_file_write_bytes:
            raise ValueError(f"Existing file is too large to checkpoint safely: {path}")
        snapshots.append({
            "path": path,
            "existed": target.is_file(),
            "original_base64": base64.b64encode(original).decode("ascii"),
            "original_sha256": _sha256(original) if target.is_file() else None,
            "applied_sha256": _sha256(encoded),
        })
        prepared.append((target, encoded, action, path))

    checkpoint_id = str(uuid.uuid4())
    checkpoint = {
        "version": 1,
        "checkpoint_id": checkpoint_id,
        "workspace": str(workspace_manager.path.resolve()),
        "created_at": datetime.now(UTC).isoformat(),
        "files": snapshots,
    }
    checkpoint_path = _checkpoint_path(checkpoint_id)
    _write_json_atomic(checkpoint_path, checkpoint)

    results = []
    try:
        for target, encoded, action, path in prepared:
            _write_bytes_atomic(target, encoded)
            results.append({"path": path, "action": action, "bytes_written": len(encoded)})
    except Exception:
        try:
            _restore_snapshot(checkpoint, verify_applied=False)
        finally:
            checkpoint_path.unlink(missing_ok=True)
        raise

    _prune_checkpoints()
    return {
        "changes": results,
        "total_bytes": total,
        "checkpoint_id": checkpoint_id,
        "undo_available": True,
    }


def undo_changes(checkpoint_id: str) -> dict[str, Any]:
    checkpoint_path, payload = _load_checkpoint(checkpoint_id)
    restored = _restore_snapshot(payload, verify_applied=True)
    checkpoint_path.unlink(missing_ok=True)
    return {
        "checkpoint_id": checkpoint_id,
        "restored": restored,
        "undo_available": False,
    }
