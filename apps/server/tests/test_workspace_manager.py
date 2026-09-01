from __future__ import annotations

from pathlib import Path

import pytest

from apps.server.app.services import workspace_manager as workspace_manager_module
from apps.server.app.services.workspace_manager import WorkspaceManager


def test_select_accepts_workspace_inside_allowed_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default_root = tmp_path / "default"
    allowed_root = tmp_path / "projects"
    repository = allowed_root / "example"
    repository.mkdir(parents=True)

    monkeypatch.setattr(workspace_manager_module.settings, "workspace_root", str(default_root))
    monkeypatch.setattr(
        workspace_manager_module.settings, "workspace_allowed_roots", str(allowed_root)
    )

    manager = WorkspaceManager()
    selected = manager.select(str(repository))

    assert manager.path == repository.resolve()
    assert selected.path == str(repository.resolve())
    assert selected.selected is True


def test_select_rejects_workspace_outside_allowed_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default_root = tmp_path / "default"
    allowed_root = tmp_path / "projects"
    outside = tmp_path / "elsewhere" / "repo"
    allowed_root.mkdir(parents=True)
    outside.mkdir(parents=True)

    monkeypatch.setattr(workspace_manager_module.settings, "workspace_root", str(default_root))
    monkeypatch.setattr(
        workspace_manager_module.settings, "workspace_allowed_roots", str(allowed_root)
    )

    manager = WorkspaceManager()

    with pytest.raises(ValueError, match="outside WORKSPACE_ALLOWED_ROOTS"):
        manager.select(str(outside))


def test_select_requires_existing_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default_root = tmp_path / "default"
    allowed_root = tmp_path / "projects"
    allowed_root.mkdir(parents=True)
    missing = allowed_root / "missing"

    monkeypatch.setattr(workspace_manager_module.settings, "workspace_root", str(default_root))
    monkeypatch.setattr(
        workspace_manager_module.settings, "workspace_allowed_roots", str(allowed_root)
    )

    manager = WorkspaceManager()

    with pytest.raises(FileNotFoundError):
        manager.select(str(missing))
