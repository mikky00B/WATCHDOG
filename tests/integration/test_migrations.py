from __future__ import annotations

import os
import subprocess
import sys

import asyncpg
import pytest


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_alembic_upgrade_head_creates_fresh_postgresql_schema() -> None:
    database_url = os.environ.get("WATCHDOG_MIGRATION_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set WATCHDOG_MIGRATION_TEST_DATABASE_URL to run fresh PostgreSQL migration test")

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
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr or result.stdout

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
    assert REQUIRED_TABLES <= created_tables
