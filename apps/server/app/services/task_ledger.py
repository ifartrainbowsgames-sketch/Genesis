from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select, update

from ..db import SessionLocal
from ..models import TaskArtifact, TaskRecord
from ..schemas import TaskSummary
from .workspace_manager import workspace_manager

logger = logging.getLogger(__name__)


def _summary(row: TaskRecord) -> TaskSummary:
    return TaskSummary(
        id=str(row.id),
        title=row.title,
        status=row.status,
        provider=row.provider,
        model=row.model,
        workspace=row.workspace,
        stop_reason=row.stop_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_task(title: str, provider: str, model: str | None) -> str:
    task_id = uuid.uuid4()
    try:
        async with SessionLocal() as session:
            session.add(TaskRecord(
                id=task_id,
                title=title,
                status="running",
                provider=provider,
                model=model,
                workspace=str(workspace_manager.path),
            ))
            await session.commit()
    except Exception as exc:
        logger.warning("Task ledger create skipped: %s", exc)
    return str(task_id)


async def add_artifact(task_id: str, kind: str, payload: Any) -> None:
    try:
        parsed = uuid.UUID(task_id)
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        async with SessionLocal() as session:
            session.add(TaskArtifact(task_id=parsed, kind=kind, payload=serialized))
            await session.commit()
    except Exception as exc:
        logger.warning("Task artifact write skipped: %s", exc)


async def finish_task(task_id: str, status: str, stop_reason: str) -> None:
    try:
        parsed = uuid.UUID(task_id)
        async with SessionLocal() as session:
            await session.execute(
                update(TaskRecord)
                .where(TaskRecord.id == parsed)
                .values(status=status, stop_reason=stop_reason)
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Task ledger update skipped: %s", exc)


async def list_tasks(limit: int = 30) -> list[TaskSummary]:
    limit = max(1, min(limit, 100))
    try:
        async with SessionLocal() as session:
            stmt = select(TaskRecord).order_by(TaskRecord.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_summary(row) for row in rows]
    except Exception as exc:
        logger.warning("Task ledger read skipped: %s", exc)
        return []
