from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import settings
from ..services.workspace_manager import workspace_manager


SKIP_PARTS = {".git", "node_modules", ".next", ".venv", "venv", "dist", "build", "target", "__pycache__"}


def _safe_path(relative_path: str) -> Path:
    root = workspace_manager.path
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path escapes workspace root")
    return candidate


def _visible(relative: Path) -> bool:
    return not any(part in SKIP_PARTS for part in relative.parts)


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
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    return {"path": path, "bytes_written": len(encoded)}


def mkdir(path: str) -> dict[str, Any]:
    target = _safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": path, "created": True}


def apply_changes(changes: list[dict[str, Any]]) -> dict[str, Any]:
    if not changes:
        raise ValueError("No changes supplied")
    if len(changes) > 50:
        raise ValueError("A single change set may contain at most 50 files")

    prepared: list[tuple[Path, bytes, str, str]] = []
    total = 0
    for change in changes:
        path = str(change.get("path", "")).strip()
        action = str(change.get("action", "replace")).strip()
        content = change.get("content")
        if not path or action not in {"create", "replace"} or not isinstance(content, str):
            raise ValueError("Each change requires path, action=create|replace, and string content")
        target = _safe_path(path)
        encoded = content.encode("utf-8")
        total += len(encoded)
        if total > settings.max_file_write_bytes:
            raise ValueError(f"Change set exceeds {settings.max_file_write_bytes} byte limit")
        if action == "create" and target.exists():
            raise FileExistsError(f"File already exists: {path}")
        prepared.append((target, encoded, action, path))

    results = []
    for target, encoded, action, path in prepared:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".genesis-tmp")
        temp.write_bytes(encoded)
        temp.replace(target)
        results.append({"path": path, "action": action, "bytes_written": len(encoded)})
    return {"changes": results, "total_bytes": total}
