from __future__ import annotations

import json
import logging
from collections.abc import Iterable

from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import MemoryKnowledge, MemoryRecord
from ..schemas import MemoryConsolidateResponse, MemoryKnowledgeHit
from .memory import embed_text

logger = logging.getLogger(__name__)


def _source_ids(value: str) -> list[str]:
    try:
        data = json.loads(value)
        return [str(item) for item in data] if isinstance(data, list) else []
    except Exception:
        return []


def _hit(row: MemoryKnowledge, score: float | None = None) -> MemoryKnowledgeHit:
    return MemoryKnowledgeHit(
        id=str(row.id),
        kind=row.kind,
        scope=row.scope,
        scope_id=row.scope_id,
        title=row.title,
        content=row.content,
        confidence=row.confidence,
        source_ids=_source_ids(row.source_ids),
        score=score,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _compact(text: str, limit: int = 600) -> str:
    value = " ".join(text.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _preference_lines(rows: Iterable[MemoryRecord]) -> list[MemoryRecord]:
    markers = (
        "prefer ",
        "i prefer",
        "always ",
        "never ",
        "do not ",
        "don't ",
        "must ",
        "should ",
        "i want ",
        "i need ",
    )
    selected: list[MemoryRecord] = []
    seen: set[str] = set()
    for row in rows:
        if row.role != "user":
            continue
        compact = _compact(row.content, 400)
        lowered = compact.lower()
        if not any(marker in lowered for marker in markers):
            continue
        key = lowered[:180]
        if key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= 12:
            break
    return selected


async def recent_knowledge(scope_id: str | None = None, limit: int = 50) -> list[MemoryKnowledgeHit]:
    limit = max(1, min(limit, 100))
    try:
        async with SessionLocal() as session:
            stmt = select(MemoryKnowledge).where(MemoryKnowledge.active.is_(True))
            if scope_id:
                stmt = stmt.where(MemoryKnowledge.scope_id == scope_id)
            rows = (await session.execute(stmt.order_by(MemoryKnowledge.updated_at.desc()).limit(limit))).scalars().all()
            return [_hit(row) for row in rows]
    except Exception as exc:
        logger.warning("Knowledge read skipped: %s", exc)
        return []


async def search_knowledge(query: str, scope_id: str | None = None, limit: int = 5) -> list[MemoryKnowledgeHit]:
    vector = await embed_text(query)
    limit = max(1, min(limit, 50))
    try:
        async with SessionLocal() as session:
            stmt = select(MemoryKnowledge).where(MemoryKnowledge.active.is_(True))
            if scope_id:
                stmt = stmt.where(MemoryKnowledge.scope_id == scope_id)
            if vector:
                distance = MemoryKnowledge.embedding.cosine_distance(vector)
                stmt = stmt.where(MemoryKnowledge.embedding.is_not(None)).order_by(distance).limit(limit)
            else:
                stmt = stmt.where(MemoryKnowledge.content.ilike(f"%{query}%")).order_by(MemoryKnowledge.updated_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_hit(row) for row in rows]
    except Exception as exc:
        logger.warning("Knowledge search skipped: %s", exc)
        return []


async def _upsert_knowledge(
    *,
    kind: str,
    scope_id: str,
    title: str,
    content: str,
    source_ids: list[str],
    confidence: float,
) -> MemoryKnowledgeHit:
    embedding = await embed_text(content)
    async with SessionLocal() as session:
        stmt = select(MemoryKnowledge).where(
            MemoryKnowledge.kind == kind,
            MemoryKnowledge.scope == "conversation",
            MemoryKnowledge.scope_id == scope_id,
            MemoryKnowledge.title == title,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = MemoryKnowledge(
                kind=kind,
                scope="conversation",
                scope_id=scope_id,
                title=title,
                content=content,
                source_ids=json.dumps(source_ids),
                confidence=confidence,
                embedding=embedding,
            )
            session.add(row)
        else:
            row.content = content
            row.source_ids = json.dumps(source_ids)
            row.confidence = confidence
            row.embedding = embedding
            row.active = True
        await session.commit()
        await session.refresh(row)
        return _hit(row)


async def consolidate_memory(conversation_id: str, max_records: int | None = None) -> MemoryConsolidateResponse:
    limit = max_records or settings.memory_consolidation_max_records
    limit = max(2, min(limit, 500))
    try:
        async with SessionLocal() as session:
            stmt = (
                select(MemoryRecord)
                .where(MemoryRecord.conversation_id == conversation_id)
                .order_by(MemoryRecord.created_at.desc())
                .limit(limit)
            )
            rows = list((await session.execute(stmt)).scalars().all())
    except Exception as exc:
        logger.warning("Memory consolidation read skipped: %s", exc)
        return MemoryConsolidateResponse(conversation_id=conversation_id, records_read=0, knowledge_written=0)

    rows.reverse()
    if len(rows) < 2:
        return MemoryConsolidateResponse(conversation_id=conversation_id, records_read=len(rows), knowledge_written=0)

    summary_rows = rows[-16:]
    summary = "\n".join(f"{row.role}: {_compact(row.content)}" for row in summary_rows)
    summary_sources = [str(row.id) for row in summary_rows]
    knowledge: list[MemoryKnowledgeHit] = [
        await _upsert_knowledge(
            kind="semantic_summary",
            scope_id=conversation_id,
            title="Conversation summary",
            content=summary,
            source_ids=summary_sources,
            confidence=min(0.95, 0.55 + len(summary_rows) * 0.02),
        )
    ]

    preferences = _preference_lines(rows)
    if preferences:
        content = "\n".join(f"- {_compact(row.content, 400)}" for row in preferences)
        knowledge.append(
            await _upsert_knowledge(
                kind="procedural",
                scope_id=conversation_id,
                title="User-stated working preferences and constraints",
                content=content,
                source_ids=[str(row.id) for row in preferences],
                confidence=0.72,
            )
        )

    return MemoryConsolidateResponse(
        conversation_id=conversation_id,
        records_read=len(rows),
        knowledge_written=len(knowledge),
        knowledge=knowledge,
    )
