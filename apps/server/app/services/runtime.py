from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import func, select

from ..db import SessionLocal
from ..models import RunEvent, TaskArtifact, TaskRecord
from ..schemas import RunEventView, TaskArtifactView, TaskDetail, TaskSummary

logger = logging.getLogger(__name__)


def _json(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _task_summary(row: TaskRecord) -> TaskSummary:
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


async def append_event(task_id: str, event_type: str, payload: Any | None = None) -> None:
    try:
        parsed = uuid.UUID(task_id)
        async with SessionLocal() as session:
            sequence = await session.scalar(
                select(func.coalesce(func.max(RunEvent.sequence), 0)).where(RunEvent.task_id == parsed)
            )
            session.add(
                RunEvent(
                    task_id=parsed,
                    sequence=int(sequence or 0) + 1,
                    event_type=event_type[:60],
                    payload=json.dumps(payload or {}, ensure_ascii=False, default=str),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Runtime event write skipped: %s", exc)


async def task_detail(task_id: str) -> TaskDetail | None:
    try:
        parsed = uuid.UUID(task_id)
    except ValueError:
        return None
    try:
        async with SessionLocal() as session:
            task = await session.get(TaskRecord, parsed)
            if not task:
                return None
            artifacts = (
                await session.execute(
                    select(TaskArtifact).where(TaskArtifact.task_id == parsed).order_by(TaskArtifact.created_at.asc())
                )
            ).scalars().all()
            events = (
                await session.execute(
                    select(RunEvent)
                    .where(RunEvent.task_id == parsed)
                    .order_by(RunEvent.sequence.asc(), RunEvent.created_at.asc())
                )
            ).scalars().all()
            return TaskDetail(
                task=_task_summary(task),
                artifacts=[
                    TaskArtifactView(id=str(row.id), kind=row.kind, payload=_json(row.payload), created_at=row.created_at)
                    for row in artifacts
                ],
                events=[
                    RunEventView(
                        id=str(row.id),
                        sequence=row.sequence,
                        event_type=row.event_type,
                        payload=_json(row.payload),
                        created_at=row.created_at,
                    )
                    for row in events
                ],
            )
    except Exception as exc:
        logger.warning("Task detail read skipped: %s", exc)
        return None


async def replay_request(task_id: str) -> dict[str, Any] | None:
    """Return the immutable team request artifact used to reproduce a task."""
    detail = await task_detail(task_id)
    if not detail:
        return None
    for artifact in detail.artifacts:
        if artifact.kind == "team_request" and isinstance(artifact.payload, dict):
            return artifact.payload
    return None
