"""Unit tests for Pydantic v2 schemas — no DB required."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from monitoring.schemas.alert import AlertCreate, AlertResponse, AlertSeverity, AlertUpdate
from monitoring.schemas.check import CheckResultCreate, CheckResultResponse
from monitoring.schemas.heartbeat import HeartbeatCreate, HeartbeatResponse, HeartbeatUpdate
from monitoring.schemas.monitor import MonitorCreate, MonitorResponse, MonitorUpdate


# ── MonitorCreate ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_monitor_create_valid() -> None:
    m = MonitorCreate(name="API", url="https://example.com", interval_seconds=60)
    assert m.name == "API"
    assert m.enabled is True
    assert m.timeout_seconds == 5.0


@pytest.mark.unit
def test_monitor_create_min_interval() -> None:
    m = MonitorCreate(name="Fast", url="https://example.com", interval_seconds=10)
    assert m.interval_seconds == 10


@pytest.mark.unit
def test_monitor_create_interval_too_low() -> None:
    with pytest.raises(Exception):  # pydantic ValidationError
        MonitorCreate(name="Bad", url="https://example.com", interval_seconds=5)


@pytest.mark.unit
def test_monitor_create_interval_too_high() -> None:
    with pytest.raises(Exception):
        MonitorCreate(name="Bad", url="https://example.com", interval_seconds=9999)


@pytest.mark.unit
def test_monitor_create_invalid_url() -> None:
    with pytest.raises(Exception):
        MonitorCreate(name="Bad", url="not-a-url", interval_seconds=60)


@pytest.mark.unit
def test_monitor_create_empty_name() -> None:
    with pytest.raises(Exception):
        MonitorCreate(name="", url="https://example.com", interval_seconds=60)


@pytest.mark.unit
def test_monitor_update_partial() -> None:
    u = MonitorUpdate(name="New Name")
    assert u.name == "New Name"
    assert u.url is None
    assert u.enabled is None


@pytest.mark.unit
def test_monitor_update_all_none() -> None:
    u = MonitorUpdate()
    d = u.model_dump(exclude_unset=True)
    assert d == {}


@pytest.mark.unit
def test_monitor_response_from_attributes() -> None:
    now = datetime.utcnow()
    data = {
        "name": "API", "url": "https://example.com",
        "monitor_type": "http", "interval_seconds": 60,
        "timeout_seconds": 5.0, "enabled": True,
        "public_id": uuid4(), "last_checked_at": None,
        "created_at": now, "updated_at": now,
    }
    resp = MonitorResponse.model_validate(data)
    assert resp.name == "API"


# ── AlertCreate / AlertResponse ───────────────────────────────────────────────

@pytest.mark.unit
def test_alert_create_valid() -> None:
    a = AlertCreate(
        monitor_id=1, severity=AlertSeverity.ERROR,
        title="Down", message="No response",
        triggered_at=datetime.utcnow(),
    )
    assert a.severity == AlertSeverity.ERROR


@pytest.mark.unit
def test_alert_create_all_severities() -> None:
    for sev in AlertSeverity:
        a = AlertCreate(
            monitor_id=1, severity=sev,
            title="T", message="M",
            triggered_at=datetime.utcnow(),
        )
        assert a.severity == sev


@pytest.mark.unit
def test_alert_create_title_too_long() -> None:
    with pytest.raises(Exception):
        AlertCreate(
            monitor_id=1, severity=AlertSeverity.INFO,
            title="x" * 501, message="M",
            triggered_at=datetime.utcnow(),
        )


@pytest.mark.unit
def test_alert_update_partial() -> None:
    u = AlertUpdate(acknowledged=True)
    d = u.model_dump(exclude_unset=True)
    assert d == {"acknowledged": True}
    assert "resolved" not in d


@pytest.mark.unit
def test_alert_severity_enum_values() -> None:
    assert AlertSeverity.INFO    == "info"
    assert AlertSeverity.WARNING == "warning"
    assert AlertSeverity.ERROR   == "error"
    assert AlertSeverity.CRITICAL == "critical"


# ── HeartbeatCreate ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_heartbeat_create_valid() -> None:
    h = HeartbeatCreate(name="Job", expected_interval_seconds=300)
    assert h.name == "Job"
    assert h.expected_interval_seconds == 300
    assert h.description is None


@pytest.mark.unit
def test_heartbeat_create_with_description() -> None:
    h = HeartbeatCreate(name="Job", description="Nightly", expected_interval_seconds=86400)
    assert h.description == "Nightly"


@pytest.mark.unit
def test_heartbeat_update_partial() -> None:
    u = HeartbeatUpdate(name="New")
    assert u.name == "New"
    assert u.expected_interval_seconds is None


# ── CheckResultCreate ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_check_result_create_success() -> None:
    c = CheckResultCreate(
        monitor_id=1, status_code=200,
        latency_ms=42.5, success=True,
    )
    assert c.success is True
    assert c.latency_ms == 42.5


@pytest.mark.unit
def test_check_result_create_failure() -> None:
    c = CheckResultCreate(
        monitor_id=1, status_code=None,
        latency_ms=None, success=False,
        error_message="Connection refused",
    )
    assert c.success is False
    assert c.error_message == "Connection refused"
