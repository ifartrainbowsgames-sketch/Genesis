from __future__ import annotations

from pathlib import Path

import pytest

from apps.server.app.tools import workspace


@pytest.fixture
def isolated_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = (tmp_path / "workspace").resolve()
    root.mkdir()
    monkeypatch.setattr(workspace.workspace_manager, "_path", root)
    monkeypatch.setattr(workspace.settings, "max_file_write_bytes", 1_000_000)
    return root


def test_safe_path_rejects_parent_traversal(isolated_workspace: Path) -> None:
    with pytest.raises(ValueError, match="Path escapes workspace root"):
        workspace.read_file("../outside.txt")


def test_safe_path_rejects_absolute_path_outside_workspace(
    isolated_workspace: Path, tmp_path: Path
) -> None:
    outside = (tmp_path / "outside.txt").resolve()
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="Path escapes workspace root"):
        workspace.read_file(str(outside))


def test_write_file_requires_explicit_overwrite(isolated_workspace: Path) -> None:
    result = workspace.write_file("notes/test.txt", "first")

    assert result == {"path": "notes/test.txt", "bytes_written": 5}
    assert (isolated_workspace / "notes" / "test.txt").read_text(encoding="utf-8") == "first"

    with pytest.raises(FileExistsError, match="overwrite=true"):
        workspace.write_file("notes/test.txt", "second")

    workspace.write_file("notes/test.txt", "second", overwrite=True)
    assert (isolated_workspace / "notes" / "test.txt").read_text(encoding="utf-8") == "second"


def test_write_file_enforces_size_limit(
    isolated_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace.settings, "max_file_write_bytes", 4)

    with pytest.raises(ValueError, match="Write exceeds 4 byte limit"):
        workspace.write_file("too-large.txt", "12345")

    assert not (isolated_workspace / "too-large.txt").exists()


def test_apply_changes_validates_entire_batch_before_writing(isolated_workspace: Path) -> None:
    (isolated_workspace / "already.txt").write_text("existing", encoding="utf-8")

    changes = [
        {"path": "would-have-been-created.txt", "action": "create", "content": "new"},
        {"path": "already.txt", "action": "create", "content": "collision"},
    ]

    with pytest.raises(FileExistsError, match="File already exists: already.txt"):
        workspace.apply_changes(changes)

    assert not (isolated_workspace / "would-have-been-created.txt").exists()
    assert (isolated_workspace / "already.txt").read_text(encoding="utf-8") == "existing"


def test_apply_changes_rejects_traversal_before_writing(isolated_workspace: Path) -> None:
    changes = [
        {"path": "safe.txt", "action": "create", "content": "safe"},
        {"path": "../escape.txt", "action": "create", "content": "escape"},
    ]

    with pytest.raises(ValueError, match="Path escapes workspace root"):
        workspace.apply_changes(changes)

    assert not (isolated_workspace / "safe.txt").exists()
    assert not (isolated_workspace.parent / "escape.txt").exists()


def test_apply_changes_enforces_total_size_limit(
    isolated_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace.settings, "max_file_write_bytes", 6)

    with pytest.raises(ValueError, match="Change set exceeds 6 byte limit"):
        workspace.apply_changes(
            [
                {"path": "one.txt", "action": "create", "content": "1234"},
                {"path": "two.txt", "action": "create", "content": "5678"},
            ]
        )

    assert not (isolated_workspace / "one.txt").exists()
    assert not (isolated_workspace / "two.txt").exists()
