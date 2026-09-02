from pathlib import Path

import pytest

from apps.server.app.services.workspace_manager import workspace_manager
from apps.server.app.tools import workspace as workspace_tools


@pytest.fixture()
def isolated_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    state = tmp_path / "genesis-state"
    monkeypatch.setattr(workspace_manager, "_path", root)
    monkeypatch.setenv("GENESIS_STATE_DIR", str(state))
    return root


def test_apply_creates_checkpoint_and_undo_restores_exact_preimages(isolated_workspace: Path) -> None:
    existing = isolated_workspace / "existing.txt"
    existing.write_text("before\n", encoding="utf-8")

    result = workspace_tools.apply_changes([
        {"path": "existing.txt", "action": "replace", "content": "after\n"},
        {"path": "new.txt", "action": "create", "content": "created\n"},
    ])

    checkpoint_id = result["checkpoint_id"]
    assert result["undo_available"] is True
    assert existing.read_text(encoding="utf-8") == "after\n"
    assert (isolated_workspace / "new.txt").read_text(encoding="utf-8") == "created\n"

    listed = workspace_tools.checkpoints()["checkpoints"]
    assert listed[0]["checkpoint_id"] == checkpoint_id
    assert set(listed[0]["paths"]) == {"existing.txt", "new.txt"}

    undone = workspace_tools.undo_changes(checkpoint_id)
    assert undone["undo_available"] is False
    assert existing.read_text(encoding="utf-8") == "before\n"
    assert not (isolated_workspace / "new.txt").exists()
    assert workspace_tools.checkpoints()["checkpoints"] == []


def test_undo_refuses_to_overwrite_user_edits_after_apply(isolated_workspace: Path) -> None:
    target = isolated_workspace / "app.py"
    target.write_text("old = True\n", encoding="utf-8")
    result = workspace_tools.apply_changes([
        {"path": "app.py", "action": "replace", "content": "new = True\n"},
    ])

    target.write_text("user_edit = True\n", encoding="utf-8")

    with pytest.raises(ValueError, match="changed after Genesis applied"):
        workspace_tools.undo_changes(result["checkpoint_id"])

    assert target.read_text(encoding="utf-8") == "user_edit = True\n"
    assert workspace_tools.checkpoints()["checkpoints"][0]["checkpoint_id"] == result["checkpoint_id"]


def test_invalid_checkpoint_id_is_rejected_without_path_access(isolated_workspace: Path) -> None:
    with pytest.raises(ValueError, match="Invalid checkpoint id"):
        workspace_tools.undo_changes("../../outside")


def test_duplicate_change_paths_are_rejected_before_writes(isolated_workspace: Path) -> None:
    with pytest.raises(ValueError, match="Duplicate change path"):
        workspace_tools.apply_changes([
            {"path": "same.txt", "action": "create", "content": "one"},
            {"path": "same.txt", "action": "replace", "content": "two"},
        ])
    assert not (isolated_workspace / "same.txt").exists()


def test_partial_apply_failure_rolls_back_all_files(isolated_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = isolated_workspace / "first.txt"
    second = isolated_workspace / "second.txt"
    first.write_text("first-before", encoding="utf-8")
    second.write_text("second-before", encoding="utf-8")

    real_write = workspace_tools._write_bytes_atomic
    calls = 0

    def fail_second_applied_write(target: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        # 1 = checkpoint JSON, 2 = first applied file, 3 = second applied file.
        if calls == 3:
            raise OSError("simulated write failure")
        real_write(target, data)

    monkeypatch.setattr(workspace_tools, "_write_bytes_atomic", fail_second_applied_write)

    with pytest.raises(OSError, match="simulated write failure"):
        workspace_tools.apply_changes([
            {"path": "first.txt", "action": "replace", "content": "first-after"},
            {"path": "second.txt", "action": "replace", "content": "second-after"},
        ])

    assert first.read_text(encoding="utf-8") == "first-before"
    assert second.read_text(encoding="utf-8") == "second-before"
    assert workspace_tools.checkpoints()["checkpoints"] == []
