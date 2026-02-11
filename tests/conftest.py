"""
Pytest configuration and shared fixtures.

Uses SQLite in-memory via aiosqlite — no running PostgreSQL required.
The async SQLAlchemy engine is swapped to SQLite for all unit tests.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from monitoring.models.base import Base

# ── SQLite in-memory engine ───────────────────────────────────────────────────
# SQLite does not support all PostgreSQL features, but is sufficient for
# unit-testing service logic and ORM queries.
# Important: "check_same_thread=False" is required for SQLite + asyncio.
SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    """Single event loop for the whole test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a fresh in-memory SQLite engine per test function."""
    engine = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session, rolled back after each test."""
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def sample_monitor(test_db: AsyncSession):
    """Persist a sample monitor for tests that need an existing record."""
    from monitoring.models.monitor import Monitor

    monitor = Monitor(
        name="Test API",
        url="https://api.example.com/health",
        interval_seconds=60,
        timeout_seconds=5.0,
        enabled=True,
    )
    test_db.add(monitor)
    await test_db.commit()
    await test_db.refresh(monitor)
    return monitor


@pytest_asyncio.fixture
async def sample_check_result(test_db: AsyncSession, sample_monitor):
    """Persist a sample check result."""
    from monitoring.models.check_result import CheckResult

    result = CheckResult(
        monitor_id=sample_monitor.id,
        status_code=200,
        latency_ms=123.4,
        success=True,
        error_message=None,
        checked_at=datetime.utcnow(),
    )
    test_db.add(result)
    await test_db.commit()
    await test_db.refresh(result)
    return result


@pytest_asyncio.fixture
async def sample_alert(test_db: AsyncSession, sample_monitor):
    """Persist a sample alert."""
    from monitoring.models.alert import Alert

    alert = Alert(
        monitor_id=sample_monitor.id,
        severity="warning",
        title="Test Alert",
        message="Something went wrong",
        resolved=False,
        acknowledged=False,
        triggered_at=datetime.utcnow(),
    )
    test_db.add(alert)
    await test_db.commit()
    await test_db.refresh(alert)
    return alert


@pytest_asyncio.fixture
async def sample_heartbeat(test_db: AsyncSession):
    """Persist a sample heartbeat."""
    from monitoring.models.heartbeat import Heartbeat

    hb = Heartbeat(
        name="Test Job",
        description="A background job",
        expected_interval_seconds=300,
    )
    test_db.add(hb)
    await test_db.commit()
    await test_db.refresh(hb)
    return hb


# ── Mock HTTP client fixture ──────────────────────────────────────────────────
@pytest.fixture
def mock_httpx_response():
    """Factory for building mock httpx responses."""
    def _make(status_code: int = 200, raise_exc=None):
        if raise_exc:
            return raise_exc
        resp = MagicMock()
        resp.status_code = status_code
        resp.raise_for_status = MagicMock()
        return resp
    return _make
