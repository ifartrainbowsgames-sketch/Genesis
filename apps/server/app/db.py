import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base
from .schema import SchemaMigrationError, migrate_schema

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
_active_schema_version: int | None = None


def database_backend() -> str:
    return engine.url.get_backend_name()


def schema_version() -> int | None:
    return _active_schema_version


async def init_db() -> None:
    global _active_schema_version
    try:
        async with engine.begin() as conn:
            if database_backend() == "postgresql":
                await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            # create_all creates a fresh database at the current model shape but does
            # not mutate existing columns. migrate_schema handles upgrades after that.
            await conn.run_sync(Base.metadata.create_all)
            _active_schema_version = await migrate_schema(conn)
    except SchemaMigrationError:
        _active_schema_version = None
        logger.exception("Genesis database schema migration failed")
        # An incompatible or partially migrated durable store is not safe to ignore.
        raise
    except Exception as exc:
        _active_schema_version = None
        logger.warning("Database unavailable; Genesis will run without durable state: %s", exc)
