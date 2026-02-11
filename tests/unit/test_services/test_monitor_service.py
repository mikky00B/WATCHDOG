"""Unit tests for MonitorService."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.monitor import Monitor
from monitoring.schemas.monitor import MonitorCreate, MonitorUpdate
from monitoring.services.monitor_service import MonitorService


@pytest.mark.unit
async def test_create_monitor(test_db: AsyncSession) -> None:
    service = MonitorService(test_db)
    data = MonitorCreate(
        name="Test Monitor",
        url="https://example.com",
        interval_seconds=60,
        timeout_seconds=5.0,
    )
    monitor = await service.create_monitor(data)

    assert monitor.id is not None
    assert monitor.name == "Test Monitor"
    assert "example.com" in monitor.url
    assert monitor.enabled is True
    assert monitor.public_id is not None


@pytest.mark.unit
async def test_create_monitor_stores_url_as_string(test_db: AsyncSession) -> None:
    """HttpUrl must be cast to str before DB insert."""
    service = MonitorService(test_db)
    data = MonitorCreate(name="URL Test", url="https://api.example.com/health", interval_seconds=30)
    monitor = await service.create_monitor(data)
    assert isinstance(monitor.url, str)


@pytest.mark.unit
async def test_get_monitor_by_public_id(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    service = MonitorService(test_db)
    found = await service.get_monitor(sample_monitor.public_id)
    assert found is not None
    assert found.id == sample_monitor.id
    assert found.name == sample_monitor.name


@pytest.mark.unit
async def test_get_monitor_not_found(test_db: AsyncSession) -> None:
    from uuid import uuid4
    service = MonitorService(test_db)
    result = await service.get_monitor(uuid4())
    assert result is None


@pytest.mark.unit
async def test_get_monitor_by_internal_id(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    service = MonitorService(test_db)
    found = await service.get_monitor_by_internal_id(sample_monitor.id)
    assert found is not None
    assert found.public_id == sample_monitor.public_id


@pytest.mark.unit
async def test_list_monitors(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    service = MonitorService(test_db)
    monitors = await service.list_monitors()
    assert len(monitors) >= 1
    assert any(m.id == sample_monitor.id for m in monitors)


@pytest.mark.unit
async def test_list_monitors_enabled_only(test_db: AsyncSession) -> None:
    service = MonitorService(test_db)
    # Create one enabled and one disabled
    await service.create_monitor(MonitorCreate(name="Enabled", url="https://a.com", interval_seconds=60))
    disabled = await service.create_monitor(MonitorCreate(name="Disabled", url="https://b.com", interval_seconds=60))
    # Disable it
    await service.update_monitor(disabled.public_id, MonitorUpdate(enabled=False))

    enabled = await service.list_monitors(enabled_only=True)
    assert all(m.enabled for m in enabled)


@pytest.mark.unit
async def test_list_monitors_pagination(test_db: AsyncSession) -> None:
    service = MonitorService(test_db)
    for i in range(5):
        await service.create_monitor(MonitorCreate(name=f"Monitor {i}", url=f"https://m{i}.com", interval_seconds=60))

    page1 = await service.list_monitors(skip=0, limit=3)
    page2 = await service.list_monitors(skip=3, limit=3)
    assert len(page1) == 3
    assert len(page2) >= 2  # at least 2 remain


@pytest.mark.unit
async def test_update_monitor(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    service = MonitorService(test_db)
    updated = await service.update_monitor(
        sample_monitor.public_id,
        MonitorUpdate(name="Updated Name", interval_seconds=120),
    )
    assert updated is not None
    assert updated.name == "Updated Name"
    assert updated.interval_seconds == 120
    # Unchanged fields preserved
    assert updated.url == sample_monitor.url


@pytest.mark.unit
async def test_update_monitor_url_cast_to_string(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    service = MonitorService(test_db)
    updated = await service.update_monitor(
        sample_monitor.public_id,
        MonitorUpdate(url="https://newurl.example.com/health"),
    )
    assert updated is not None
    assert isinstance(updated.url, str)
    assert "newurl.example.com" in updated.url


@pytest.mark.unit
async def test_update_monitor_not_found(test_db: AsyncSession) -> None:
    from uuid import uuid4
    service = MonitorService(test_db)
    result = await service.update_monitor(uuid4(), MonitorUpdate(name="Ghost"))
    assert result is None


@pytest.mark.unit
async def test_delete_monitor(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    service = MonitorService(test_db)
    deleted = await service.delete_monitor(sample_monitor.public_id)
    assert deleted is True
    assert await service.get_monitor(sample_monitor.public_id) is None


@pytest.mark.unit
async def test_delete_monitor_not_found(test_db: AsyncSession) -> None:
    from uuid import uuid4
    service = MonitorService(test_db)
    result = await service.delete_monitor(uuid4())
    assert result is False
