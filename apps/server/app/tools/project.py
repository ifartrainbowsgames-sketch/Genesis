from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..config import settings


CHECKS: dict[str, tuple[list[str], str | None]] = {
    "python_compile": (["python", "-m", "compileall", "."], None),
    "python_test": (["python", "-m", "pytest", "-q"], None),
    "npm_build": (["npm", "run", "build"], None),
    "npm_test": (["npm", "test", "--", "--runInBand"], None),
    "cargo_check": (["cargo", "check"], None),
    "cargo_test": (["cargo", "test"], None),
}


def _safe_cwd(relative_cwd: str) -> Path:
    root = settings.workspace_path
    cwd = (root / relative_cwd).resolve()
    if cwd != root and root not in cwd.parents:
        raise ValueError("Working directory escapes workspace root")
    if not cwd.is_dir():
        raise FileNotFoundError(relative_cwd)
    return cwd


def detect_checks() -> dict[str, Any]:
    root = settings.workspace_path
    available: list[dict[str, str]] = []
    for path in root.rglob("package.json"):
        if "node_modules" in path.parts:
            continue
        available.append({"kind": "npm_build", "cwd": str(path.parent.relative_to(root)).replace("\\", "/") or "."})
    for path in root.rglob("pyproject.toml"):
        available.append({"kind": "python_test", "cwd": str(path.parent.relative_to(root)).replace("\\", "/") or "."})
    for path in root.rglob("requirements.txt"):
        available.append({"kind": "python_compile", "cwd": str(path.parent.relative_to(root)).replace("\\", "/") or "."})
    for path in root.rglob("Cargo.toml"):
        available.append({"kind": "cargo_check", "cwd": str(path.parent.relative_to(root)).replace("\\", "/") or "."})
    return {"checks": available[:50]}


def run_check(kind: str, cwd: str = ".", timeout_seconds: int = 180) -> dict[str, Any]:
    if kind not in CHECKS:
        raise ValueError(f"Unsupported check: {kind}")
    timeout_seconds = max(1, min(timeout_seconds, 600))
    command, _ = CHECKS[kind]
    workdir = _safe_cwd(cwd)
    try:
        result = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required executable not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Check timed out after {timeout_seconds}s") from exc

    output = (result.stdout + "\n" + result.stderr).strip()
    if len(output) > 100_000:
        output = output[-100_000:]
    return {
        "kind": kind,
        "cwd": cwd,
        "command": command,
        "exit_code": result.returncode,
        "output": output,
        "passed": result.returncode == 0,
    }
