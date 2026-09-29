from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.monitor import Monitor
from monitoring.models.organization import Organization
from monitoring.models.user import User
from monitoring.schemas.auth import RegisterRequest
from monitoring.schemas.status_page import StatusPageCreate, StatusPageServiceCreate, StatusPageUpdate
from monitoring.services.auth_service import AuthService
from monitoring.services.status_page_service import StatusPageService


@pytest.mark.unit
async def test_auth_service_core_branches(test_db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    service = AuthService(test_db)
    monkeypatch.setattr(service, "_send_verification_email", AsyncMock(return_value=True))
    user = await service.register(
        RegisterRequest(full_name="Auth User", email="AUTH@EXAMPLE.COM", password="StrongPass123")
    )
    assert user.email == "auth@example.com"
    assert await service.get_user_by_email("AUTH@example.com") is user
    assert await service.get_user_by_public_id("bad-id") is None
    assert await service.authenticate(user.email, "wrong") is None
    assert await service.authenticate(user.email, "StrongPass123") is user

    monkeypatch.setattr(service, "_new_verification_code", staticmethod(lambda: "123456"))
    assert await service.resend_verification_code(user.email) is user
    assert await service.verify_email(user.email, "000000") is None
    assert await service.verify_email(user.email, "123456") is user
    assert await service.resend_verification_code("missing@example.com") is None

    token = await service.create_refresh_session(user)
    assert await service.refresh_access_token(token) is not None
    assert await service.revoke_refresh_token("missing") is False
    assert await service.revoke_refresh_token(token) is True
    assert await service.refresh_access_token(token) is None

    monkeypatch.setattr(service, "_send_password_reset_email", AsyncMock(return_value=True))
    assert await service.request_password_reset(user.email) is user
    assert await service.reset_password(user.email, "bad", "NewStrongPass123") is None

    from monitoring.core.security import hash_password_reset_code
    user.password_reset_expires_at = datetime.now(UTC) + timedelta(minutes=10)
    user.password_reset_code_hash = hash_password_reset_code(user.email, "123456")
    await test_db.flush()
    assert await service.reset_password(user.email, "123456", "NewStrongPass123") is user
    assert await service.authenticate(user.email, "NewStrongPass123") is user


@pytest.mark.unit
async def test_auth_service_inactive_and_expired(test_db: AsyncSession) -> None:
    service = AuthService(test_db)
    user = User(
        full_name="Inactive",
        email="inactive@example.com",
        password_hash="invalid",
        is_active=False,
    )
    test_db.add(user)
    await test_db.flush()
    assert await service.authenticate(user.email, "x") is None
    assert await service.resend_verification_code(user.email) is None
    assert await service.verify_email(user.email, "123456") is None
    assert await service.request_password_reset(user.email) is None

    user.is_active = True
    user.email_verification_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    user.email_verification_code_hash = "bad"
    await test_db.flush()
    assert await service.verify_email(user.email, "123456") is None


@pytest.mark.unit
async def test_status_page_service_lifecycle(test_db: AsyncSession) -> None:
    user = User(full_name="Owner", email="status@example.com", password_hash="hash")
    test_db.add(user)
    await test_db.flush()
    org = Organization(name="Status Org", slug="status-org", owner_id=user.id)
    test_db.add(org)
    await test_db.flush()

    service = StatusPageService(test_db)
    page = await service.create_status_page(
        StatusPageCreate(organization_id=org.public_id, name="Public Status", slug="public-status")
    )
    with pytest.raises(ValueError, match="already in use"):
        await service.create_status_page(
            StatusPageCreate(organization_id=org.public_id, name="Duplicate", slug="public-status")
        )

    pages, total = await service.list_status_pages(org.id)
    assert total == 1 and pages[0].id == page.id

    monitor = Monitor(
        organization_id=org.id,
        name="Website",
        url="https://example.com",
        interval_seconds=60,
        status="UP",
    )
    test_db.add(monitor)
    await test_db.flush()
    page_service = await service.add_service(
        page.public_id,
        StatusPageServiceCreate(monitor_id=monitor.public_id, display_name="Website", sort_order=1),
    )
    assert page_service is not None
    services, total = await service.list_services(page.public_id)
    assert total == 1 and services[0].display_name == "Website"

    updated = await service.update_status_page(
        page.public_id, StatusPageUpdate(name="Updated", slug="updated-status")
    )
    assert updated is not None and updated.name == "Updated"

    public_page = await service.get_public_status_page("updated-status")
    assert public_page is not None and public_page["overall_status"] == "OPERATIONAL"
    monitor.status = "DEGRADED"
    await test_db.flush()
    public_page = await service.get_public_status_page("updated-status")
    assert public_page is not None and public_page["overall_status"] == "DEGRADED"
    monitor.status = "DOWN"
    await test_db.flush()
    public_page = await service.get_public_status_page("updated-status")
    assert public_page is not None and public_page["overall_status"] == "MAJOR_OUTAGE"

    assert await service.delete_service(page.public_id, page_service.public_id) is True
    assert await service.delete_service(page.public_id, page_service.public_id) is False
    assert await service.delete_status_page(page.public_id) is True
    assert await service.delete_status_page(page.public_id) is False
    assert await service.get_public_status_page("updated-status") is None


@pytest.mark.unit
async def test_status_page_invalid_inputs(test_db: AsyncSession) -> None:
    service = StatusPageService(test_db)
    import uuid
    with pytest.raises(ValueError, match="Organization not found"):
        await service.create_status_page(
            StatusPageCreate(organization_id=uuid.uuid4(), name="Missing", slug="missing")
        )
    assert await service.get_status_page(uuid.uuid4()) is None
    assert await service.get_status_page_by_slug("missing") is None
    assert await service.list_services(uuid.uuid4()) is None
    assert await service.delete_status_page(uuid.uuid4()) is False


@pytest.mark.unit
async def test_rule_engine_additional_rule_types(test_db: AsyncSession, sample_monitor: Monitor) -> None:
    from datetime import timedelta
    from monitoring.models.check_result import CheckResult
    from monitoring.schemas.alert import AlertSeverity
    from monitoring.services.rule_engine import (
        ErrorRateRule, LatencyThresholdRule, RuleConfig, RuleEngine, RuleType,
        StatusCodePatternRule, UptimePercentageRule, create_default_rules,
    )

    assert len(create_default_rules()) == 4
    with pytest.raises(ValueError):
        RuleConfig(rule_type=RuleType.ERROR_RATE, threshold=0)
    with pytest.raises(ValueError):
        RuleConfig(rule_type=RuleType.ERROR_RATE, threshold=1, window_minutes=0)

    now = datetime.now(UTC)
    latest = CheckResult(
        monitor_id=sample_monitor.id, success=False, status_code=500,
        latency_ms=2500, error_message="server error", checked_at=now,
    )
    test_db.add(latest)
    await test_db.flush()

    latency = LatencyThresholdRule(RuleConfig(
        rule_type=RuleType.LATENCY_THRESHOLD, threshold=100,
        metadata={"require_sustained": False},
    ))
    alert = await latency.evaluate(sample_monitor, latest, test_db)
    assert alert is not None

    status_rule = StatusCodePatternRule(RuleConfig(
        rule_type=RuleType.STATUS_CODE_PATTERN, threshold=1,
        metadata={"status_codes": [500]}, severity=AlertSeverity.ERROR,
    ))
    alert = await status_rule.evaluate(sample_monitor, latest, test_db)
    assert alert is not None

    uptime = UptimePercentageRule(RuleConfig(
        rule_type=RuleType.UPTIME_PERCENTAGE, threshold=95, window_minutes=60,
    ))
    for i in range(10):
        test_db.add(CheckResult(
            monitor_id=sample_monitor.id, success=i != 0,
            status_code=200 if i else 500, latency_ms=10,
            checked_at=now - timedelta(seconds=i),
        ))
    await test_db.flush()
    assert await uptime.evaluate(sample_monitor, latest, test_db) is not None

    error_rate = ErrorRateRule(RuleConfig(
        rule_type=RuleType.ERROR_RATE, threshold=5, window_minutes=60,
    ))
    assert await error_rate.evaluate(sample_monitor, latest, test_db) is not None

    engine = RuleEngine()
    engine.register_rules(sample_monitor.id, [
        latency,
        StatusCodePatternRule(RuleConfig(
            rule_type=RuleType.STATUS_CODE_PATTERN, threshold=1,
            enabled=False, metadata={"status_codes": [500]},
        )),
    ])
    assert len(await engine.get_monitor_rules(sample_monitor.id)) == 1
    alerts = await engine.evaluate_all(sample_monitor, latest, test_db)
    assert alerts
    engine.clear_alert_cache(sample_monitor.id)
    engine.unregister_rules(sample_monitor.id)
    assert await engine.get_monitor_rules(sample_monitor.id) == []


@pytest.mark.unit
async def test_monitor_service_heartbeat_and_stats(test_db: AsyncSession) -> None:
    from monitoring.schemas.monitor import MonitorCreate
    from monitoring.services.monitor_service import MonitorService
    from monitoring.models.check_result import CheckResult

    service = MonitorService(test_db)
    heartbeat = await service.create_monitor(MonitorCreate(
        name="Heartbeat", monitor_type="HEARTBEAT", interval_seconds=60,
    ))
    assert heartbeat.heartbeat_key
    assert await service.get_monitor_by_heartbeat_key(heartbeat.heartbeat_key) is heartbeat
    assert await service.ping_heartbeat_monitor(heartbeat.heartbeat_key) is heartbeat
    assert await service.ping_heartbeat_monitor("missing") is None

    http_monitor = await service.create_monitor(MonitorCreate(
        name="Stats", url="https://stats.example.com", interval_seconds=60,
    ))
    test_db.add_all([
        CheckResult(monitor_id=http_monitor.id, success=True, status_code=200, latency_ms=10, checked_at=datetime.now(UTC)),
        CheckResult(monitor_id=http_monitor.id, success=False, status_code=500, latency_ms=None, error_message="down", checked_at=datetime.now(UTC)),
    ])
    await test_db.flush()
    stats = await service.get_stats(http_monitor.public_id)
    assert stats is not None and stats["failed_checks"] == 1
    assert await service.get_stats(__import__("uuid").uuid4()) is None
    assert await service.list_check_results(__import__("uuid").uuid4()) is None


@pytest.mark.unit
def test_monitoring_exception_messages() -> None:
    from monitoring.utils.exceptions import (
        AlertDeliveryError, AlertNotFoundError, CheckError,
        HeartbeatNotFoundError, MonitorNotFoundError,
    )
    assert str(MonitorNotFoundError(1)) == "Monitor 1 not found"
    assert str(MonitorNotFoundError("x")) == "Monitor x not found"
    assert str(AlertNotFoundError(2)) == "Alert 2 not found"
    assert str(HeartbeatNotFoundError("hb")) == "Heartbeat hb not found"
    assert str(CheckError(3, "timeout")) == "Check failed for monitor 3: timeout"
    assert str(AlertDeliveryError(4, "email", "failed")) == "Failed to deliver alert 4 via email: failed"
