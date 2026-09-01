from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from ..config import settings
from ..schemas import TeamRunRequest, WorkerInfo, WorkerRunRequest, WorkerRunResponse
from .team import run_team
from .workspace_manager import workspace_manager


WorkerType = Literal["command", "http"]


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    type: WorkerType
    argv: tuple[str, ...] = ()
    url: str | None = None
    cwd: str = "."
    timeout_seconds: int = settings.external_worker_timeout_seconds
    token_env: str | None = None
    input_mode: Literal["text", "json"] = "text"


def _safe_cwd(relative: str) -> Path:
    root = workspace_manager.path
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Worker cwd escapes workspace root")
    if not candidate.is_dir():
        raise FileNotFoundError(relative)
    return candidate


def _parse_workers() -> dict[str, WorkerSpec]:
    try:
        raw = json.loads(settings.external_workers_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("EXTERNAL_WORKERS_JSON is invalid JSON") from exc
    if not isinstance(raw, list):
        raise ValueError("EXTERNAL_WORKERS_JSON must be a JSON array")

    workers: dict[str, WorkerSpec] = {}
    for item in raw:
        if not isinstance(item, dict) or not item.get("enabled", True):
            continue
        name = str(item.get("name", "")).strip()
        worker_type = str(item.get("type", "")).strip()
        if not name or worker_type not in {"command", "http"}:
            raise ValueError("Each worker needs a name and type=command|http")
        timeout = max(1, min(int(item.get("timeout_seconds", settings.external_worker_timeout_seconds)), 1800))
        input_mode = str(item.get("input_mode", "text"))
        if input_mode not in {"text", "json"}:
            raise ValueError(f"Worker {name} input_mode must be text or json")
        if worker_type == "command":
            argv = item.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
                raise ValueError(f"Command worker {name} requires a non-empty argv array")
            workers[name] = WorkerSpec(
                name=name,
                type="command",
                argv=tuple(argv),
                cwd=str(item.get("cwd", ".")),
                timeout_seconds=timeout,
                input_mode=input_mode,  # type: ignore[arg-type]
            )
        else:
            url = str(item.get("url", "")).strip()
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"HTTP worker {name} requires a valid http(s) URL")
            workers[name] = WorkerSpec(
                name=name,
                type="http",
                url=url,
                timeout_seconds=timeout,
                token_env=str(item.get("token_env")) if item.get("token_env") else None,
                input_mode=input_mode,  # type: ignore[arg-type]
            )
    return workers


def list_workers() -> list[WorkerInfo]:
    result = [WorkerInfo(name="genesis-team", type="builtin", detail="Bounded Architect/Researcher/Builder/Reviewer team")]
    for worker in _parse_workers().values():
        detail = "Fixed argv subprocess; shell disabled" if worker.type == "command" else "Allowlisted HTTP worker"
        result.append(WorkerInfo(name=worker.name, type=worker.type, detail=detail))
    return result


def worker_count() -> int:
    return 1 + len(_parse_workers())


def _bounded_output(value: str) -> str:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= settings.external_worker_max_output_bytes:
        return value
    return encoded[-settings.external_worker_max_output_bytes :].decode("utf-8", errors="replace")


async def _run_command(spec: WorkerSpec, request: WorkerRunRequest) -> WorkerRunResponse:
    cwd = _safe_cwd(spec.cwd)
    payload = (
        json.dumps({"prompt": request.prompt, "context": request.context}, ensure_ascii=False)
        if spec.input_mode == "json"
        else request.prompt
    )
    process = await asyncio.create_subprocess_exec(
        *spec.argv,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(payload.encode("utf-8")), timeout=spec.timeout_seconds)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RuntimeError(f"Worker {spec.name} timed out after {spec.timeout_seconds}s") from exc
    output = (stdout + (b"\n" + stderr if stderr else b"")).decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise RuntimeError(f"Worker {spec.name} exited with code {process.returncode}: {_bounded_output(output)}")
    return WorkerRunResponse(
        worker=spec.name,
        output=_bounded_output(output),
        metadata={"type": "command", "exit_code": process.returncode, "argv": list(spec.argv)},
    )


async def _run_http(spec: WorkerSpec, request: WorkerRunRequest) -> WorkerRunResponse:
    headers = {"content-type": "application/json"}
    if spec.token_env:
        token = os.environ.get(spec.token_env)
        if not token:
            raise RuntimeError(f"Worker {spec.name} requires environment variable {spec.token_env}")
        headers["authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=spec.timeout_seconds, follow_redirects=False) as client:
        response = await client.post(
            spec.url or "",
            headers=headers,
            json={"prompt": request.prompt, "context": request.context},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data: Any = response.json()
            output = data.get("output") if isinstance(data, dict) else None
            if output is None:
                output = json.dumps(data, ensure_ascii=False)
        else:
            output = response.text
    return WorkerRunResponse(
        worker=spec.name,
        output=_bounded_output(str(output)),
        metadata={"type": "http", "status_code": response.status_code},
    )


async def run_worker(request: WorkerRunRequest) -> WorkerRunResponse:
    if request.worker == "genesis-team":
        team = await run_team(
            TeamRunRequest(
                task=request.prompt,
                provider=request.provider,
                model=request.model,
                use_research=request.use_research,
            )
        )
        return WorkerRunResponse(
            worker="genesis-team",
            output=json.dumps(team.model_dump(mode="json"), ensure_ascii=False),
            task_id=team.task_id,
            metadata={"type": "builtin", "status": team.status},
        )

    spec = _parse_workers().get(request.worker)
    if not spec:
        raise KeyError(f"Unknown worker: {request.worker}")
    if spec.type == "command":
        return await _run_command(spec, request)
    return await _run_http(spec, request)
