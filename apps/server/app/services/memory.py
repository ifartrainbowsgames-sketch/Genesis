from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy import delete, select

from ..config import settings
from ..db import SessionLocal
from ..models import MemoryRecord
from ..schemas import MemoryHit

logger = logging.getLogger(__name__)


async def embed_text(text: str) -> list[float] | None:
    base = settings.ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{base}/api/embed",
                json={"model": settings.ollama_embed_model, "input": text, "dimensions": settings.embedding_dim},
            )
            if response.is_success:
                data = response.json()
                embeddings = data.get("embeddings") or []
                if embeddings:
                    vector = embeddings[0]
                    return vector if len(vector) == settings.embedding_dim else None
        except Exception:
            pass

        try:
            response = await client.post(f"{base}/api/embeddings", json={"model": settings.ollama_embed_model, "prompt": text})
            if response.is_success:
                vector = response.json().get("embedding")
                return vector if vector and len(vector) == settings.embedding_dim else None
        except Exception as exc:
            logger.debug("Embedding unavailable: %s", exc)
    return None


def _hit(row: MemoryRecord, score: float | None = None) -> MemoryHit:
    return MemoryHit(
        id=str(row.id),
        conversation_id=row.conversation_id,
        role=row.role,
        content=row.content,
        score=score,
        created_at=row.created_at,
    )


async def remember(conversation_id: str, role: str, content: str) -> None:
    vector = await embed_text(content)
    try:
        async with SessionLocal() as session:
            session.add(MemoryRecord(conversation_id=conversation_id, role=role, content=content, embedding=vector))
            await session.commit()
    except Exception as exc:
        logger.warning("Memory write skipped: %s", exc)


async def recent_memory(conversation_id: str | None = None, limit: int = 50) -> list[MemoryHit]:
    limit = max(1, min(limit, 100))
    try:
        async with SessionLocal() as session:
            stmt = select(MemoryRecord)
            if conversation_id:
                stmt = stmt.where(MemoryRecord.conversation_id == conversation_id)
            stmt = stmt.order_by(MemoryRecord.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_hit(row) for row in rows]
    except Exception as exc:
        logger.warning("Memory read skipped: %s", exc)
        return []


async def search_memory(query: str, conversation_id: str | None = None, limit: int = 5) -> list[MemoryHit]:
    vector = await embed_text(query)
    try:
        async with SessionLocal() as session:
            stmt = select(MemoryRecord)
            if conversation_id:
                stmt = stmt.where(MemoryRecord.conversation_id == conversation_id)

            if vector:
                distance = MemoryRecord.embedding.cosine_distance(vector)
                stmt = stmt.where(MemoryRecord.embedding.is_not(None)).order_by(distance).limit(limit)
                rows = (await session.execute(stmt)).scalars().all()
                return [_hit(row) for row in rows]

            stmt = stmt.where(MemoryRecord.content.ilike(f"%{query}%")).order_by(MemoryRecord.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_hit(row) for row in rows]
    except Exception as exc:
        logger.warning("Memory search skipped: %s", exc)
        return []


async def delete_memory(memory_id: str) -> bool:
    try:
        parsed = uuid.UUID(memory_id)
    except ValueError as exc:
        raise ValueError("Invalid memory id") from exc
    try:
        async with SessionLocal() as session:
            result = await session.execute(delete(MemoryRecord).where(MemoryRecord.id == parsed))
            await session.commit()
            return bool(result.rowcount)
    except Exception as exc:
        logger.warning("Memory delete failed: %s", exc)
        return False


async def clear_memory(conversation_id: str | None = None) -> int:
    try:
        async with SessionLocal() as session:
            stmt = delete(MemoryRecord)
            if conversation_id:
                stmt = stmt.where(MemoryRecord.conversation_id == conversation_id)
            result = await session.execute(stmt)
            await session.commit()
            return int(result.rowcount or 0)
    except Exception as exc:
        logger.warning("Memory clear failed: %s", exc)
        return 0
