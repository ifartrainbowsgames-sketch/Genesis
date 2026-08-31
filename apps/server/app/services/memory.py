from __future__ import annotations

import logging

import httpx
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import MemoryRecord
from ..schemas import MemoryHit

logger = logging.getLogger(__name__)


async def embed_text(text: str) -> list[float] | None:
    base = settings.ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Current Ollama API.
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
            # Compatibility with older Ollama versions.
            response = await client.post(f"{base}/api/embeddings", json={"model": settings.ollama_embed_model, "prompt": text})
            if response.is_success:
                vector = response.json().get("embedding")
                return vector if vector and len(vector) == settings.embedding_dim else None
        except Exception as exc:
            logger.debug("Embedding unavailable: %s", exc)
    return None


async def remember(conversation_id: str, role: str, content: str) -> None:
    vector = await embed_text(content)
    try:
        async with SessionLocal() as session:
            session.add(MemoryRecord(conversation_id=conversation_id, role=role, content=content, embedding=vector))
            await session.commit()
    except Exception as exc:
        logger.warning("Memory write skipped: %s", exc)


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
                return [
                    MemoryHit(
                        id=str(row.id),
                        conversation_id=row.conversation_id,
                        role=row.role,
                        content=row.content,
                        score=None,
                    )
                    for row in rows
                ]

            stmt = stmt.where(MemoryRecord.content.ilike(f"%{query}%")).order_by(MemoryRecord.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                MemoryHit(
                    id=str(row.id),
                    conversation_id=row.conversation_id,
                    role=row.role,
                    content=row.content,
                    score=None,
                )
                for row in rows
            ]
    except Exception as exc:
        logger.warning("Memory search skipped: %s", exc)
        return []
