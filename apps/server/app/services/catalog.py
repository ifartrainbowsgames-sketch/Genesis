from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import CatalogInstallation, CatalogTransaction
from ..schemas import CatalogEntry, CatalogManifest

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "catalog" / "index.json"


def compute_manifest_hash(manifest: CatalogManifest) -> str:
    canonical = json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_raw() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"Catalog index not found at {CATALOG_PATH}")
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Catalog index must contain an 'entries' array")
    return entries


def load_manifests() -> dict[str, CatalogManifest]:
    manifests: dict[str, CatalogManifest] = {}
    for raw in _load_raw():
        manifest = CatalogManifest.model_validate(raw)
        if manifest.app_id in manifests:
            raise ValueError(f"Duplicate catalog app_id: {manifest.app_id}")
        manifests[manifest.app_id] = manifest
    return manifests


def get_manifest(app_id: str) -> CatalogManifest:
    manifest = load_manifests().get(app_id)
    if not manifest:
        raise KeyError(f"Unknown catalog app: {app_id}")
    return manifest


def freshness_ok(manifest: CatalogManifest, now: datetime | None = None) -> bool:
    reference = now or datetime.now(timezone.utc)
    age_seconds = (reference - manifest.published_at).total_seconds()
    return age_seconds >= settings.catalog_freshness_hours * 3600


async def _installed_rows() -> dict[str, CatalogInstallation]:
    try:
        async with SessionLocal() as session:
            rows = (await session.execute(select(CatalogInstallation))).scalars().all()
            return {row.app_id: row for row in rows}
    except Exception as exc:
        logger.warning("Catalog install-state read skipped: %s", exc)
        return {}


async def list_catalog() -> dict[str, Any]:
    manifests = load_manifests()
    installed = await _installed_rows()
    entries: list[dict[str, Any]] = []
    for app_id, manifest in manifests.items():
        row = installed.get(app_id)
        entries.append(
            CatalogEntry(
                manifest=manifest,
                manifest_hash=compute_manifest_hash(manifest),
                installed=bool(row and row.status == "installed"),
                installed_version=row.version if row else None,
                status=row.status if row else None,
            ).model_dump(mode="json")
        )
    return {"entries": entries}


async def _record_transaction(app_id: str, phase: str, detail: dict[str, Any]) -> None:
    try:
        async with SessionLocal() as session:
            session.add(
                CatalogTransaction(
                    app_id=app_id,
                    phase=phase,
                    detail=json.dumps(detail, ensure_ascii=False, default=str),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Catalog transaction log skipped: %s", exc)


async def _upsert_installation(app_id: str, version: str, manifest_hash: str, status: str) -> None:
    try:
        async with SessionLocal() as session:
            existing = (
                await session.execute(select(CatalogInstallation).where(CatalogInstallation.app_id == app_id))
            ).scalar_one_or_none()
            if existing:
                existing.version = version
                existing.manifest_hash = manifest_hash
                existing.status = status
            else:
                session.add(
                    CatalogInstallation(app_id=app_id, version=version, manifest_hash=manifest_hash, status=status)
                )
            await session.commit()
    except Exception as exc:
        logger.warning("Catalog install-state write skipped: %s", exc)


def _install_argv(manifest: CatalogManifest) -> list[str]:
    if manifest.install_type == "winget":
        winget_id = manifest.source.get("winget_id")
        if not winget_id:
            raise ValueError(f"{manifest.app_id} manifest missing source.winget_id")
        return [
            "winget", "install", "--exact", "--id", str(winget_id),
            "--silent", "--accept-package-agreements", "--accept-source-agreements", "--scope", "user",
        ]
    if manifest.install_type == "ollama_pull":
        model = manifest.source.get("model")
        if not model:
            raise ValueError(f"{manifest.app_id} manifest missing source.model")
        return ["ollama", "pull", str(model)]
    raise ValueError(f"Unsupported install_type: {manifest.install_type}")


def _uninstall_argv(manifest: CatalogManifest) -> list[str] | None:
    if manifest.uninstall_command:
        return list(manifest.uninstall_command)
    if manifest.install_type == "winget":
        winget_id = manifest.source.get("winget_id")
        if winget_id:
            return ["winget", "uninstall", "--exact", "--id", str(winget_id), "--silent"]
    if manifest.install_type == "ollama_pull":
        model = manifest.source.get("model")
        if model:
            return ["ollama", "rm", str(model)]
    return None


async def _run_fixed(argv: list[str], timeout_seconds: int) -> dict[str, Any]:
    try:
        process = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required executable not found: {argv[0]}") from exc
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RuntimeError(f"Command timed out after {timeout_seconds}s: {' '.join(argv)}") from exc
    output = (stdout + (b"\n" + stderr if stderr else b"")).decode("utf-8", errors="replace").strip()
    if len(output) > 50_000:
        output = output[-50_000:]
    return {"argv": argv, "exit_code": process.returncode, "output": output}


async def install_app(app_id: str, manifest_hash: str) -> dict[str, Any]:
    manifest = get_manifest(app_id)
    expected_hash = compute_manifest_hash(manifest)
    if manifest_hash != expected_hash:
        raise ValueError("Catalog entry changed since approval; re-propose the install")
    if not freshness_ok(manifest):
        raise ValueError(f"{app_id} was published too recently and is not yet installable (freshness delay)")

    await _record_transaction(app_id, "stage", {"version": manifest.version})
    argv = _install_argv(manifest)
    try:
        result = await _run_fixed(argv, settings.catalog_install_timeout_seconds)
    except RuntimeError as exc:
        await _record_transaction(app_id, "rollback", {"error": str(exc)})
        await _upsert_installation(app_id, manifest.version, expected_hash, "failed")
        raise

    if result["exit_code"] != 0:
        await _record_transaction(app_id, "rollback", result)
        await _upsert_installation(app_id, manifest.version, expected_hash, "failed")
        raise RuntimeError(f"Install failed for {app_id}: exit {result['exit_code']}: {result['output'][-500:]}")

    await _record_transaction(app_id, "commit", result)
    await _upsert_installation(app_id, manifest.version, expected_hash, "installed")
    return {"app_id": app_id, "status": "installed", "detail": result["output"][-2000:]}


async def launch_app(app_id: str, manifest_hash: str) -> dict[str, Any]:
    manifest = get_manifest(app_id)
    if manifest_hash != compute_manifest_hash(manifest):
        raise ValueError("Catalog entry changed since approval; re-propose the launch")
    if not manifest.launch_command:
        raise ValueError(f"{app_id} has no launch command; installing makes it available directly (e.g. as a chat model)")
    exe = manifest.launch_command[0]
    if not shutil.which(exe):
        raise RuntimeError(f"{exe} was not found on PATH; install {app_id} first")
    try:
        subprocess.Popen(manifest.launch_command, shell=False)
    except OSError as exc:
        raise RuntimeError(f"Failed to launch {app_id}: {exc}") from exc
    await _record_transaction(app_id, "launch", {"argv": manifest.launch_command})
    return {"app_id": app_id, "status": "launched"}


async def uninstall_app(app_id: str) -> dict[str, Any]:
    manifest = get_manifest(app_id)
    argv = _uninstall_argv(manifest)
    if not argv:
        raise ValueError(f"{app_id} has no uninstall path defined")
    result = await _run_fixed(argv, settings.catalog_install_timeout_seconds)
    if result["exit_code"] != 0:
        await _record_transaction(app_id, "rollback", result)
        raise RuntimeError(f"Uninstall failed for {app_id}: exit {result['exit_code']}: {result['output'][-500:]}")
    await _record_transaction(app_id, "commit", {"action": "uninstall", **result})
    await _upsert_installation(app_id, manifest.version, compute_manifest_hash(manifest), "uninstalled")
    return {"app_id": app_id, "status": "uninstalled"}
