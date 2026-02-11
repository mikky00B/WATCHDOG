"""Unit tests for HeartbeatService."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.heartbeat import Heartbeat
from monitoring.schemas.heartbeat import HeartbeatCreate, HeartbeatUpdate
from monitoring.services.heartbeat_service import HeartbeatService


@pytest.mark.unit
async def test_create_heartbeat(test_db: AsyncSession) -> None:
    service = HeartbeatService(test_db)
    hb = await service.create_heartbeat(HeartbeatCreate(
        name="My Job", description="Nightly run", expected_interval_seconds=3600
    ))
    assert hb.id is not None
    assert hb.name == "My Job"
    assert hb.expected_interval_seconds == 3600
    assert hb.public_id is not None
    assert hb.last_heartbeat_at is None


@pytest.mark.unit
async def test_get_heartbeat(test_db: AsyncSession, sample_heartbeat: Heartbeat) -> None:
    service = HeartbeatService(test_db)
    found = await service.get_heartbeat(sample_heartbeat.public_id)
    assert found is not None
    assert found.id == sample_heartbeat.id


@pytest.mark.unit
async def test_get_heartbeat_not_found(test_db: AsyncSession) -> None:
    from uuid import uuid4
    service = HeartbeatService(test_db)
    assert await service.get_heartbeat(uuid4()) is None


@pytest.mark.unit
async def test_list_heartbeats(test_db: AsyncSession, sample_heartbeat: Heartbeat) -> None:
    service = HeartbeatService(test_db)
    items = await service.list_heartbeats()
    assert any(h.id == sample_heartbeat.id for h in items)


@pytest.mark.unit
async def test_update_heartbeat(test_db: AsyncSession, sample_heartbeat: Heartbeat) -> None:
    service = HeartbeatService(test_db)
    updated = await service.update_heartbeat(
        sample_heartbeat.public_id,
        HeartbeatUpdate(name="Updated Job", expected_interval_seconds=600),
    )
    assert updated is not None
    assert updated.name == "Updated Job"
    assert updated.expected_interval_seconds == 600


@pytest.mark.unit
async def test_update_heartbeat_not_found(test_db: AsyncSession) -> None:
    from uuid import uuid4
    service = HeartbeatService(test_db)
    assert await service.update_heartbeat(uuid4(), HeartbeatUpdate(name="Ghost")) is None


@pytest.mark.unit
async def test_delete_heartbeat(test_db: AsyncSession, sample_heartbeat: Heartbeat) -> None:
    service = HeartbeatService(test_db)
    assert await service.delete_heartbeat(sample_heartbeat.public_id) is True
    assert await service.get_heartbeat(sample_heartbeat.public_id) is None


@pytest.mark.unit
async def test_delete_heartbeat_not_found(test_db: AsyncSession) -> None:
    from uuid import uuid4
    service = HeartbeatService(test_db)
    assert await service.delete_heartbeat(uuid4()) is False


@pytest.mark.unit
async def test_ping_heartbeat(test_db: AsyncSession, sample_heartbeat: Heartbeat) -> None:
    service = HeartbeatService(test_db)
    assert sample_heartbeat.last_heartbeat_at is None
    pinged = await service.ping_heartbeat(sample_heartbeat.public_id)
    assert pinged is not None
    assert pinged.last_heartbeat_at is not None


@pytest.mark.unit
async def test_ping_heartbeat_not_found(test_db: AsyncSession) -> None:
    from uuid import uuid4
    service = HeartbeatService(test_db)
    assert await service.ping_heartbeat(uuid4()) is None
