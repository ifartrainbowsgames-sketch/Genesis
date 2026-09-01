from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from ..config import settings


SKIP_DIRS = {".git", "node_modules", ".next", ".venv", "venv", "dist", "build", "target", "__pycache__"}


@dataclass(frozen=True)
class WorkspaceCandidate:
    name: str
    path: str
    is_git: bool
    selected: bool


class WorkspaceManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._path = settings.workspace_path

    @property
    def path(self) -> Path:
        with self._lock:
            return self._path

    def _allowed_roots(self) -> list[Path]:
        roots = [settings.workspace_path]
        raw = settings.workspace_allowed_roots.strip()
        if raw:
            parts: list[str] = []
            for chunk in raw.replace(os.pathsep, ";").split(";"):
                if chunk.strip():
                    parts.append(chunk.strip())
            roots.extend(Path(item).expanduser().resolve() for item in parts)
        deduped: list[Path] = []
        for root in roots:
            if root not in deduped:
                deduped.append(root)
        return deduped

    def _is_allowed(self, candidate: Path) -> bool:
        for root in self._allowed_roots():
            if candidate == root or root in candidate.parents:
                return True
        return False

    def select(self, path: str) -> WorkspaceCandidate:
        candidate = Path(path).expanduser().resolve()
        if not self._is_allowed(candidate):
            raise ValueError("Workspace is outside WORKSPACE_ALLOWED_ROOTS")
        if not candidate.exists() or not candidate.is_dir():
            raise FileNotFoundError(path)
        with self._lock:
            self._path = candidate
        return self.describe(candidate)

    def describe(self, path: Path | None = None) -> WorkspaceCandidate:
        target = (path or self.path).resolve()
        return WorkspaceCandidate(
            name=target.name or str(target),
            path=str(target),
            is_git=(target / ".git").exists(),
            selected=target == self.path,
        )

    def discover(self, max_depth: int = 3, limit: int = 80) -> list[WorkspaceCandidate]:
        found: dict[str, WorkspaceCandidate] = {}
        current = self.path
        found[str(current)] = self.describe(current)

        for root in self._allowed_roots():
            if not root.exists() or not root.is_dir():
                continue
            root_depth = len(root.parts)
            for base, dirnames, _ in os.walk(root):
                base_path = Path(base)
                depth = len(base_path.parts) - root_depth
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
                if depth >= max_depth:
                    dirnames[:] = []
                if (base_path / ".git").exists():
                    item = self.describe(base_path)
                    found[item.path] = item
                    dirnames[:] = []
                if len(found) >= limit:
                    break
            if len(found) >= limit:
                break

        return sorted(found.values(), key=lambda item: (not item.selected, item.name.lower(), item.path.lower()))[:limit]


workspace_manager = WorkspaceManager()
