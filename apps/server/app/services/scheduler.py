from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from ..config import settings
from ..db import SessionLocal
from ..models import ScheduleRecord
from ..schemas import ScheduleCreateRequest, ScheduleInfo, TeamRunRequest
from .team import run_team

logger = logging.getLogger(__name__)
_scheduler_task: asyncio.Task[None] | None = None


def _decode_request(payload: str) -> TeamRunRequest:
    return TeamRunRequest.model_validate(json.loads(payload))


def _info(row: ScheduleRecord) -> ScheduleInfo:
    return ScheduleInfo(
        id=str(row.id),
        name=row.name,
        enabled=row.enabled,
        request=_decode_request(row.request_payload),
        interval_seconds=row.interval_seconds,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_task_id=str(row.last_task_id) if row.last_task_id else None,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_schedule(request: ScheduleCreateRequest) -> ScheduleInfo:
    now = datetime.now(timezone.utc)
    next_run = now if request.run_immediately else now + timedelta(seconds=request.interval_seconds)
    row = ScheduleRecord(
        name=request.name,
        enabled=True,
        request_payload=json.dumps(request.request.model_dump(mode="json"), ensure_ascii=False),
        interval_seconds=request.interval_seconds,
        next_run_at=next_run,
    )
    async with SessionLocal() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return _info(row)


async def list_schedules() -> list[ScheduleInfo]:
    try:
        async with SessionLocal() as session:
            rows = (await session.execute(select(ScheduleRecord).order_by(ScheduleRecord.created_at.asc()))).scalars().all()
            return [_info(row) for row in rows]
    except Exception as exc:
        logger.warning("Schedule read skipped: %s", exc)
        return []


async def set_schedule_enabled(schedule_id: str, enabled: bool) -> ScheduleInfo | None:
    try:
        parsed = uuid.UUID(schedule_id)
    except ValueError:
        return None
    async with SessionLocal() as session:
        row = await session.get(ScheduleRecord, parsed)
        if not row:
            return None
        row.enabled = enabled
        if enabled and row.next_run_at < datetime.now(timezone.utc):
            row.next_run_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        return _info(row)


async def delete_schedule(schedule_id: str) -> bool:
    try:
        parsed = uuid.UUID(schedule_id)
    except ValueError:
        return False
    async with SessionLocal() as session:
        row = await session.get(ScheduleRecord, parsed)
        if not row:
            return False
        await session.delete(row)
        await session.commit()
        return True


async def run_due_schedules(limit: int = 5) -> list[str]:
    now = datetime.now(timezone.utc)
    triggered: list[str] = []
    try:
        async with SessionLocal() as session:
            stmt = (
                select(ScheduleRecord)
                .where(ScheduleRecord.enabled.is_(True), ScheduleRecord.next_run_at <= now)
                .order_by(ScheduleRecord.next_run_at.asc())
                .limit(max(1, min(limit, 20)))
                .with_for_update(skip_locked=True)
            )
            rows = (await session.execute(stmt)).scalars().all()
            # Move next_run_at before executing so a slow run cannot be picked twice.
            for row in rows:
                row.next_run_at = now + timedelta(seconds=row.interval_seconds)
            await session.commit()

        for row in rows:
            last_error: str | None = None
            task_uuid: uuid.UUID | None = None
            try:
                response = await run_team(_decode_request(row.request_payload))
                task_uuid = uuid.UUID(response.task_id)
                triggered.append(response.task_id)
            except Exception as exc:
                last_error = str(exc)[:4000]
                logger.warning("Scheduled run %s failed: %s", row.id, exc)
            async with SessionLocal() as session:
                await session.execute(
                    update(ScheduleRecord)
                    .where(ScheduleRecord.id == row.id)
                    .values(last_run_at=now, last_task_id=task_uuid, last_error=last_error)
                )
                await session.commit()
    except Exception as exc:
        logger.warning("Schedule scan skipped: %s", exc)
    return triggered


async def _loop() -> None:
    poll = max(5, min(settings.scheduler_poll_seconds, 300))
    while True:
        try:
            await run_due_schedules()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Scheduler iteration failed: %s", exc)
        await asyncio.sleep(poll)


def start_scheduler() -> None:
    global _scheduler_task
    if not settings.scheduler_enabled or (_scheduler_task and not _scheduler_task.done()):
        return
    _scheduler_task = asyncio.create_task(_loop(), name="genesis-scheduler")


async def stop_scheduler() -> None:
    global _scheduler_task
    if not _scheduler_task:
        return
    _scheduler_task.cancel()
    try:
        await _scheduler_task
    except asyncio.CancelledError:
        pass
    _scheduler_task = None


def scheduler_state() -> dict:
    running = bool(_scheduler_task and not _scheduler_task.done())
    return {"enabled": settings.scheduler_enabled, "running": running, "poll_seconds": settings.scheduler_poll_seconds}
