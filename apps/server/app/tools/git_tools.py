from __future__ import annotations

import subprocess
from typing import Any

from ..config import settings


def _git(args: list[str], timeout: int = 20) -> str:
    root = settings.workspace_path
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(output or f"git exited with code {result.returncode}")
    return output


def status() -> dict[str, Any]:
    return {"output": _git(["status", "--short", "--branch"])}


def diff(staged: bool = False, path: str | None = None) -> dict[str, Any]:
    args = ["diff"]
    if staged:
        args.append("--staged")
    if path:
        args.extend(["--", path])
    return {"output": _git(args)}
