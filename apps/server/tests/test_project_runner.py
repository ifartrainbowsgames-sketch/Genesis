from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from apps.server.app.tools import project


@pytest.fixture
def project_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = (tmp_path / "workspace").resolve()
    root.mkdir()
    monkeypatch.setattr(project.workspace_manager, "_path", root)
    return root


def test_run_check_rejects_arbitrary_commands(project_workspace: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported check"):
        project.run_check("powershell -Command Remove-Item")


def test_run_check_rejects_cwd_traversal(project_workspace: Path) -> None:
    with pytest.raises(ValueError, match="Working directory escapes workspace root"):
        project.run_check("python_test", cwd="..")


def test_run_check_uses_fixed_command_without_shell(
    project_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = project_workspace / "server"
    workdir.mkdir()
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(project.subprocess, "run", fake_run)

    result = project.run_check("python_test", cwd="server", timeout_seconds=9999)

    assert captured["command"] == ["python", "-m", "pytest", "-q"]
    assert captured["cwd"] == workdir
    assert captured["shell"] is False
    assert captured["timeout"] == 600
    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert result["output"] == "ok"


def test_run_check_reports_nonzero_exit_without_throwing(
    project_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="tests failed")

    monkeypatch.setattr(project.subprocess, "run", fake_run)

    result = project.run_check("python_compile")

    assert result["passed"] is False
    assert result["exit_code"] == 2
    assert result["output"] == "tests failed"
