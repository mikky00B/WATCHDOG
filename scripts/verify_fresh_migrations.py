"""Verify that Alembic can bootstrap a clean PostgreSQL schema.

This script drops and recreates the ``public`` schema for the database pointed
to by WATCHDOG_MIGRATION_TEST_DATABASE_URL, then runs ``alembic upgrade head``.
Use only a disposable database.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import asyncpg


REQUIRED_TABLES = {
    "alembic_version",
    "alerts",
    "alert_events",
    "auth_sessions",
    "check_results",
    "clients",
    "heartbeats",
    "incident_updates",
    "incidents",
    "monitors",
    "notification_channels",
    "organization_members",
    "organizations",
    "status_page_services",
    "status_pages",
    "users",
}


def _asyncpg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def main() -> int:
    database_url = os.environ.get("WATCHDOG_MIGRATION_TEST_DATABASE_URL")
    if not database_url:
        print("Set WATCHDOG_MIGRATION_TEST_DATABASE_URL to a disposable PostgreSQL database URL.")
        return 2

    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        await connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await connection.execute("CREATE SCHEMA public")
    finally:
        await connection.close()

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        env=env,
    )
    if result.returncode != 0:
        return result.returncode

    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        rows = await connection.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
    finally:
        await connection.close()

    created_tables = {row["table_name"] for row in rows}
    missing = sorted(REQUIRED_TABLES - created_tables)
    if missing:
        print(f"Missing tables after migration: {', '.join(missing)}")
        return 1

    print("Fresh Alembic migration verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
