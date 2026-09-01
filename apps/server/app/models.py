import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings


class Base(DeclarativeBase):
    pass


class MemoryRecord(Base):
    __tablename__ = "memory_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[str] = mapped_column(String(200), index=True, default="default")
    role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class TaskRecord(Base):
    __tablename__ = "task_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    provider: Mapped[str] = mapped_column(String(40), default="ollama")
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    workspace: Mapped[str] = mapped_column(Text)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)


class TaskArtifact(Base):
    __tablename__ = "task_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("task_records.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
