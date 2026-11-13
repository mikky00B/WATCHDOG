"""Schema validation tests for the extended monitor configuration."""

from __future__ import annotations

import pytest
from monitoring.schemas.monitor import MonitorCreate, MonitorUpdate
from pydantic import ValidationError


class TestMonitorTypeValidation:
    def test_all_types_accepted(self) -> None:
        for monitor_type, url in [
            ("WEBSITE", "https://example.com"),
            ("API", "https://api.example.com"),
            ("HEARTBEAT", None),
            ("SSL", "https://example.com"),
            ("DNS", "example.com"),
            ("TCP", "tcp://db.example.com"),
        ]:
            payload = {"name": "M", "monitor_type": monitor_type, "interval_seconds": 60}
            if url is not None:
                payload["url"] = url
            if monitor_type == "TCP":
                payload["port"] = 5432
            monitor = MonitorCreate(**payload)
            assert monitor.monitor_type == monitor_type

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MonitorCreate(name="M", monitor_type="PING", url="https://x.com", interval_seconds=60)

    def test_http_alias_normalizes(self) -> None:
        monitor = MonitorCreate(name="M", monitor_type="HTTP", url="https://x.com", interval_seconds=60)
        assert monitor.monitor_type == "WEBSITE"

    def test_http_type_requires_http_url(self) -> None:
        with pytest.raises(ValidationError):
            MonitorCreate(name="M", monitor_type="WEBSITE", url="not-a-url", interval_seconds=60)

    def test_tcp_requires_port(self) -> None:
        with pytest.raises(ValidationError):
            MonitorCreate(name="M", monitor_type="TCP", url="tcp://db.example.com", interval_seconds=60)

    def test_dns_defaults_record_type(self) -> None:
        monitor = MonitorCreate(name="M", monitor_type="DNS", url="example.com", interval_seconds=60)
        assert monitor.record_type == "A"

    def test_dns_invalid_record_type(self) -> None:
        with pytest.raises(ValidationError):
            MonitorCreate(
                name="M",
                monitor_type="DNS",
                url="example.com",
                record_type="BOGUS",
                interval_seconds=60,
            )

    def test_url_required_for_non_heartbeat(self) -> None:
        with pytest.raises(ValidationError):
            MonitorCreate(name="M", monitor_type="TCP", interval_seconds=60)


class TestTagNormalization:
    def test_tags_stripped_and_deduplicated(self) -> None:
        monitor = MonitorCreate(
            name="M",
            url="https://example.com",
            interval_seconds=60,
            tags=["prod", " prod ", "PROD", ""],
        )
        assert monitor.tags == ["prod", "PROD"]

    def test_empty_tags_become_none(self) -> None:
        monitor = MonitorCreate(name="M", url="https://example.com", interval_seconds=60, tags=["  "])
        assert monitor.tags is None

    def test_long_tag_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MonitorCreate(
                name="M",
                url="https://example.com",
                interval_seconds=60,
                tags=["x" * 51],
            )

    def test_environment_accepted(self) -> None:
        monitor = MonitorCreate(
            name="M",
            url="https://example.com",
            interval_seconds=60,
            environment="production",
        )
        assert monitor.environment == "production"


class TestMonitorUpdate:
    def test_partial_update_fields(self) -> None:
        update = MonitorUpdate(tags=["one", "two"], environment="staging")
        assert update.tags == ["one", "two"]
        assert update.environment == "staging"
        assert update.name is None

    def test_update_type_validation(self) -> None:
        update = MonitorUpdate(monitor_type="tcp")
        assert update.monitor_type == "TCP"
        with pytest.raises(ValidationError):
            MonitorUpdate(monitor_type="SMTP")
