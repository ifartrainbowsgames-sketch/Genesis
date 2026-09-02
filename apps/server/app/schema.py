from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


CURRENT_SCHEMA_VERSION = 1
Migration = Callable[[AsyncConnection], Awaitable[None]]


class SchemaMigrationError(RuntimeError):
    pass


# A migration upgrades schema N-1 -> N. Version 1 is the Genesis 0.10 baseline,
# created directly from SQLAlchemy metadata. Future schema changes must register
# a migration here instead of relying on create_all() to alter existing tables.
MIGRATIONS: dict[int, Migration] = {}


async def _ensure_version_table(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS genesis_schema_version (
                singleton INTEGER PRIMARY KEY,
                version INTEGER NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


async def read_schema_version(connection: AsyncConnection) -> int | None:
    await _ensure_version_table(connection)
    result = await connection.execute(
        text("SELECT version FROM genesis_schema_version WHERE singleton = 1")
    )
    row = result.first()
    return int(row[0]) if row is not None else None


async def _write_schema_version(connection: AsyncConnection, version: int) -> None:
    existing = await read_schema_version(connection)
    if existing is None:
        await connection.execute(
            text(
                "INSERT INTO genesis_schema_version (singleton, version) VALUES (1, :version)"
            ),
            {"version": version},
        )
        return

    await connection.execute(
        text(
            """
            UPDATE genesis_schema_version
            SET version = :version, updated_at = CURRENT_TIMESTAMP
            WHERE singleton = 1
            """
        ),
        {"version": version},
    )


async def migrate_schema(
    connection: AsyncConnection,
    *,
    target_version: int = CURRENT_SCHEMA_VERSION,
    migrations: dict[int, Migration] | None = None,
) -> int:
    if target_version < 1:
        raise SchemaMigrationError("Genesis schema version must be at least 1")

    current = await read_schema_version(connection)

    # Fresh databases have just been created from the current SQLAlchemy metadata,
    # so they can be stamped directly at the app's current schema version.
    if current is None:
        await _write_schema_version(connection, target_version)
        return target_version

    if current > target_version:
        raise SchemaMigrationError(
            f"Database schema version {current} is newer than this Genesis build ({target_version}). "
            "Upgrade Genesis instead of opening the database with an older build."
        )

    registry = MIGRATIONS if migrations is None else migrations
    for next_version in range(current + 1, target_version + 1):
        migration = registry.get(next_version)
        if migration is None:
            raise SchemaMigrationError(
                f"No database migration is registered for schema version {next_version}"
            )
        await migration(connection)
        await _write_schema_version(connection, next_version)

    return target_version
