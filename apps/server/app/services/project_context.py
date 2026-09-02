from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from .workspace_manager import SKIP_DIRS, workspace_manager


TEXT_EXTENSIONS = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".md", ".toml",
    ".yaml", ".yml", ".css", ".scss", ".html", ".txt", ".ini", ".cfg", ".rs", ".go", ".java",
    ".c", ".h", ".cpp", ".hpp", ".sh", ".ps1", ".sql",
}
SPECIAL_TEXT_NAMES = {"Dockerfile", "Makefile", "Procfile", "AGENTS.md", "requirements.txt"}
MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile", "tsconfig.json", "README.md", "AGENTS.md",
}
SENSITIVE_NAMES = {".env", ".env.local", ".env.production", ".npmrc", "id_rsa", "id_ed25519"}
MAX_INDEX_FILES = 5_000
MAX_SYMBOL_FILE_BYTES = 256_000
MAX_CONTEXT_FILE_BYTES = 80_000


@dataclass(frozen=True)
class IndexedFile:
    path: str
    size: int
    mtime_ns: int
    sha256: str
    extension: str
    symbols: tuple[str, ...]
    manifest: bool


_lock = RLock()
_cache_root = ""
_cache: dict[str, IndexedFile] = {}
_last_indexed_at = ""


def _eligible(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if any(part in SKIP_DIRS or part.startswith(".") and part not in {".github"} for part in relative.parts[:-1]):
        return False
    if path.name in SENSITIVE_NAMES or path.name.endswith((".pem", ".key", ".p12", ".pfx", ".crt")):
        return False
    return path.name in SPECIAL_TEXT_NAMES or path.suffix.lower() in TEXT_EXTENSIONS


def _language(path: str) -> str:
    name = Path(path).name
    if name in {"Dockerfile", "Makefile", "Procfile"}:
        return name.lower()
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix or "text"


def _symbols(path: Path, data: bytes) -> tuple[str, ...]:
    if len(data) > MAX_SYMBOL_FILE_BYTES:
        return ()
    text = data.decode("utf-8", errors="replace")
    suffix = path.suffix.lower()
    patterns: list[re.Pattern[str]] = []
    if suffix in {".py", ".pyi"}:
        patterns = [re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)]
    elif suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
        patterns = [
            re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)", re.M),
            re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=", re.M),
        ]
    elif suffix == ".rs":
        patterns = [re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|struct|enum|trait|type)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)]
    elif suffix == ".go":
        patterns = [re.compile(r"^\s*(?:func|type)\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)", re.M)]
    elif suffix in {".java", ".c", ".h", ".cpp", ".hpp"}:
        patterns = [re.compile(r"\b(?:class|struct|enum|interface)\s+([A-Za-z_][A-Za-z0-9_]*)")]

    found: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group(1)
            if value not in found:
                found.append(value)
            if len(found) >= 80:
                return tuple(found)
    return tuple(found)


def refresh_index() -> dict[str, Any]:
    global _cache_root, _cache, _last_indexed_at
    root = workspace_manager.path.resolve()
    root_key = str(root)
    with _lock:
        previous = _cache if _cache_root == root_key else {}
        next_cache: dict[str, IndexedFile] = {}
        changed = 0
        reused = 0
        total_bytes = 0
        languages: dict[str, int] = {}
        manifests: list[str] = []

        for path in root.rglob("*"):
            if len(next_cache) >= MAX_INDEX_FILES:
                break
            if not path.is_file() or not _eligible(path, root):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            relative = str(path.relative_to(root)).replace("\\", "/")
            cached = previous.get(relative)
            if cached and cached.size == stat.st_size and cached.mtime_ns == stat.st_mtime_ns:
                item = cached
                reused += 1
            else:
                try:
                    data = path.read_bytes()
                except OSError:
                    continue
                item = IndexedFile(
                    path=relative,
                    size=len(data),
                    mtime_ns=stat.st_mtime_ns,
                    sha256=hashlib.sha256(data).hexdigest(),
                    extension=_language(relative),
                    symbols=_symbols(path, data),
                    manifest=path.name in MANIFEST_NAMES,
                )
                changed += 1
            next_cache[relative] = item
            total_bytes += item.size
            languages[item.extension] = languages.get(item.extension, 0) + 1
            if item.manifest:
                manifests.append(relative)

        removed = max(0, len(previous) - len(next_cache))
        _cache_root = root_key
        _cache = next_cache
        _last_indexed_at = datetime.now(UTC).isoformat()
        return {
            "workspace": root_key,
            "indexed_at": _last_indexed_at,
            "file_count": len(next_cache),
            "total_bytes": total_bytes,
            "changed_files": changed,
            "reused_files": reused,
            "removed_files": removed,
            "languages": dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
            "manifests": sorted(manifests),
            "truncated": len(next_cache) >= MAX_INDEX_FILES,
        }


def snapshot() -> dict[str, Any]:
    summary = refresh_index()
    with _lock:
        symbol_count = sum(len(item.symbols) for item in _cache.values())
        top_symbols = [
            {"path": item.path, "symbols": list(item.symbols[:12])}
            for item in _cache.values()
            if item.symbols
        ][:40]
    return {**summary, "symbol_count": symbol_count, "symbol_files": top_symbols}


def _tokens(query: str) -> list[str]:
    return [token for token in re.findall(r"[A-Za-z0-9_$.-]+", query.lower()) if len(token) >= 2][:40]


def search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    refresh_index()
    tokens = _tokens(query)
    with _lock:
        items = list(_cache.values())

    scored: list[tuple[int, IndexedFile]] = []
    for item in items:
        path_lower = item.path.lower()
        symbol_lower = [symbol.lower() for symbol in item.symbols]
        score = 5 if item.manifest else 0
        for token in tokens:
            if token in path_lower:
                score += 8
            if any(token in symbol for symbol in symbol_lower):
                score += 12
        if score > 0 or not tokens and item.manifest:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].size, pair[1].path))
    return [
        {
            "path": item.path,
            "size": item.size,
            "sha256": item.sha256,
            "symbols": list(item.symbols),
            "manifest": item.manifest,
            "score": score,
        }
        for score, item in scored[: max(1, min(limit, 50))]
    ]


def context_for(query: str, max_files: int = 24, max_total_chars: int = 120_000) -> tuple[str, list[str]]:
    hits = search(query, limit=max_files)
    root = workspace_manager.path.resolve()
    sections: list[str] = []
    used: list[str] = []
    total = 0
    for hit in hits:
        path = root / str(hit["path"])
        try:
            if path.stat().st_size > MAX_CONTEXT_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        block = f"\n--- FILE: {hit['path']} ---\n{text}\n"
        if total + len(block) > max_total_chars:
            break
        sections.append(block)
        used.append(str(hit["path"]))
        total += len(block)
    if not sections:
        return "(no bounded project context matched this request)", []
    return "".join(sections), used


def compact_summary(query: str = "") -> str:
    info = snapshot()
    hits = search(query, limit=12) if query.strip() else []
    lines = [
        f"Workspace: {info['workspace']}",
        f"Indexed files: {info['file_count']} ({info['total_bytes']} bytes)",
        "Languages: " + ", ".join(f"{name}:{count}" for name, count in list(info["languages"].items())[:8]),
        "Manifests: " + (", ".join(info["manifests"][:12]) or "none"),
    ]
    if hits:
        lines.append("Likely relevant files: " + ", ".join(str(hit["path"]) for hit in hits[:12]))
    return "\n".join(lines)
