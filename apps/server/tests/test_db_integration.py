from __future__ import annotations

import asyncio
import os

import pytest

from apps.server.app.db import SessionLocal, init_db
from apps.server.app.models import MemoryRecord
from apps.server.app.schemas import ScheduleCreateRequest, TeamRunRequest
from apps.server.app.services import memory_consolidator
from apps.server.app.services.runtime import task_detail
from apps.server.app.services.scheduler import create_schedule, delete_schedule
from apps.server.app.services.task_ledger import add_artifact, create_task, finish_task

pytestmark = pytest.mark.skipif(
    os.getenv("GENESIS_RUN_DB_INTEGRATION") != "1",
    reason="Set GENESIS_RUN_DB_INTEGRATION=1 with PostgreSQL/pgvector available to run database integration tests",
)


async def _no_embedding(_: str):
    return None


async def _exercise_runtime() -> None:
    await init_db()

    task_id = await create_task("integration task", "ollama", None)
    await add_artifact(task_id, "integration", {"ok": True})
    await finish_task(task_id, "complete", "integration finished")
    detail = await task_detail(task_id)
    assert detail is not None
    assert detail.task.status == "complete"
    assert [artifact.kind for artifact in detail.artifacts] == ["integration"]
    assert [event.event_type for event in detail.events] == [
        "task.started",
        "artifact.created",
        "task.status",
    ]

    async with SessionLocal() as session:
        session.add_all(
            [
                MemoryRecord(conversation_id="integration", role="user", content="I prefer concise release notes."),
                MemoryRecord(conversation_id="integration", role="assistant", content="Understood."),
                MemoryRecord(conversation_id="integration", role="user", content="Never auto-promote prompt changes."),
            ]
        )
        await session.commit()

    original = memory_consolidator.embed_text
    memory_consolidator.embed_text = _no_embedding
    try:
        consolidated = await memory_consolidator.consolidate_memory("integration", 20)
    finally:
        memory_consolidator.embed_text = original
    assert consolidated.records_read == 3
    assert consolidated.knowledge_written == 2
    assert {item.kind for item in consolidated.knowledge} == {"semantic_summary", "procedural"}

    schedule = await create_schedule(
        ScheduleCreateRequest(
            name="integration schedule",
            request=TeamRunRequest(task="bounded scheduled task", max_agent_calls=1),
            interval_seconds=60,
        )
    )
    assert schedule.enabled is True
    assert schedule.interval_seconds == 60
    assert await delete_schedule(schedule.id) is True


def test_postgres_pgvector_runtime_integration() -> None:
    asyncio.run(_exercise_runtime())
