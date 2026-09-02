from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from apps.server.app.schema import SchemaMigrationError, migrate_schema, read_schema_version


async def _fresh_schema() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            version = await migrate_schema(connection, target_version=1, migrations={})
            assert version == 1
            assert await read_schema_version(connection) == 1
    finally:
        await engine.dispose()


def test_fresh_database_is_stamped_at_current_model_version() -> None:
    asyncio.run(_fresh_schema())


async def _upgrade_schema() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def migration_2(connection: AsyncConnection) -> None:
        await connection.execute(text("CREATE TABLE migration_probe (id INTEGER PRIMARY KEY)"))

    try:
        async with engine.begin() as connection:
            await migrate_schema(connection, target_version=1, migrations={})
            version = await migrate_schema(connection, target_version=2, migrations={2: migration_2})
            assert version == 2
            assert await read_schema_version(connection) == 2
            probe = await connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='migration_probe'")
            )
            assert probe.scalar_one() == "migration_probe"
    finally:
        await engine.dispose()


def test_registered_migration_runs_in_order_and_advances_version() -> None:
    asyncio.run(_upgrade_schema())


async def _missing_migration() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await migrate_schema(connection, target_version=1, migrations={})
            with pytest.raises(SchemaMigrationError, match="No database migration"):
                await migrate_schema(connection, target_version=2, migrations={})
            assert await read_schema_version(connection) == 1
    finally:
        await engine.dispose()


def test_missing_migration_refuses_to_silently_advance_schema() -> None:
    asyncio.run(_missing_migration())


async def _newer_database() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await migrate_schema(connection, target_version=3, migrations={})
            with pytest.raises(SchemaMigrationError, match="newer than this Genesis build"):
                await migrate_schema(connection, target_version=2, migrations={})
            assert await read_schema_version(connection) == 3
    finally:
        await engine.dispose()


def test_older_build_refuses_database_from_newer_genesis() -> None:
    asyncio.run(_newer_database())
