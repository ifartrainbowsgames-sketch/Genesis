import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def database_backend() -> str:
    return engine.url.get_backend_name()


async def init_db() -> None:
    try:
        async with engine.begin() as conn:
            if database_backend() == "postgresql":
                await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        logger.warning("Database unavailable; Genesis will run without durable state: %s", exc)
