"""Tests for the new monitor types and advanced assertions in CheckerService."""

from __future__ import annotations

import ssl as ssl_module
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.services.checker_service import (
    _cert_issuer_common_name,
    _extract_json_path,
    _parse_cert_date,
    apply_check_result_to_monitor,
)


def _make_monitor(**kwargs) -> Monitor:
    defaults = {
        "id": 1,
        "name": "Test",
        "url": "https://api.example.com",
        "monitor_type": "WEBSITE",
        "interval_seconds": 60,
        "timeout_seconds": 5.0,
    }
    defaults.update(kwargs)
    return Monitor(**defaults)


def _make_httpx_response(
    status_code: int = 200,
    json_body: object | None = None,
    headers: dict[str, str] | None = None,
    text: str = "ok",
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.headers = headers or {}
    if json_body is not None:
        response.json = MagicMock(return_value=json_body)
    else:
        response.json = MagicMock(side_effect=ValueError("no json"))
    return response


class TestExtractJsonPath:
    def test_flat_key(self) -> None:
        assert _extract_json_path({"status": "ok"}, "status") == "ok"

    def test_nested_path(self) -> None:
        body = {"data": {"status": "ok", "items": [{"id": 7}]}}
        assert _extract_json_path(body, "data.status") == "ok"
        assert _extract_json_path(body, "data.items.0.id") == 7

    def test_missing_key_raises(self) -> None:
        with pytest.raises(KeyError):
            _extract_json_path({"a": 1}, "a.b")

    def test_bad_list_index_raises(self) -> None:
        with pytest.raises(KeyError):
            _extract_json_path({"items": [1]}, "items.5")


class TestCertHelpers:
    def test_parse_cert_date(self) -> None:
        parsed = _parse_cert_date("Jun  1 12:00:00 2026 GMT")
        assert parsed.year == 2026 and parsed.month == 6 and parsed.day == 1
        assert parsed.tzinfo is UTC

    def test_issuer_common_name(self) -> None:
        cert = {"issuer": ((("commonName", "R11"),), (("organizationName", "Let's Encrypt"),))}
        assert _cert_issuer_common_name(cert) == "R11"


class TestApplyCheckResultToMonitor:
    def test_ssl_metadata_synced(self) -> None:
        monitor = _make_monitor(monitor_type="SSL", ssl_expiry_threshold_days=14)
        expires = datetime.now(UTC) + timedelta(days=30)
        result = CheckResult(
            monitor_id=1,
            success=True,
            meta={
                "ssl_expires_at": expires.isoformat(),
                "ssl_issuer": "Let's Encrypt",
                "ssl_days_remaining": 30.0,
            },
            checked_at=datetime.now(UTC),
        )
        apply_check_result_to_monitor(monitor, result)
        assert monitor.ssl_issuer == "Let's Encrypt"
        assert monitor.ssl_expires_at is not None

    def test_expiring_marks_degraded(self) -> None:
        monitor = _make_monitor(monitor_type="SSL", ssl_expiry_threshold_days=14)
        result = CheckResult(
            monitor_id=1,
            success=True,
            meta={
                "ssl_expires_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
                "ssl_issuer": "R11",
                "ssl_days_remaining": 5.0,
            },
            checked_at=datetime.now(UTC),
        )
        apply_check_result_to_monitor(monitor, result)
        assert monitor.status == "DEGRADED"

    def test_expired_marks_down(self) -> None:
        monitor = _make_monitor(monitor_type="SSL")
        result = CheckResult(
            monitor_id=1,
            success=False,
            meta={
                "ssl_expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                "ssl_issuer": "R11",
                "ssl_days_remaining": -1.0,
            },
            checked_at=datetime.now(UTC),
        )
        apply_check_result_to_monitor(monitor, result)
        assert monitor.status == "DOWN"

    def test_non_ssl_meta_is_noop(self) -> None:
        monitor = _make_monitor(status="UNKNOWN")
        result = CheckResult(monitor_id=1, success=True, checked_at=datetime.now(UTC))
        apply_check_result_to_monitor(monitor, result)
        assert monitor.ssl_expires_at is None
        assert monitor.status == "UNKNOWN"


class TestAdvancedAssertions:
    def _checker(self):
        from monitoring.services.checker_service import CheckerService

        return CheckerService()

    def test_expected_header_missing(self) -> None:
        checker = self._checker()
        monitor = _make_monitor(expected_headers={"X-Custom": "yes"})
        success, reason = checker._evaluate_response(
            monitor,
            _make_httpx_response(headers={"Other": "1"}),
        )
        assert not success
        assert "X-Custom" in (reason or "")

    def test_expected_header_value_mismatch(self) -> None:
        checker = self._checker()
        monitor = _make_monitor(expected_headers={"X-Custom": "yes"})
        success, reason = checker._evaluate_response(
            monitor,
            _make_httpx_response(headers={"X-Custom": "no"}),
        )
        assert not success
        assert "X-Custom" in (reason or "")

    def test_expected_header_match(self) -> None:
        checker = self._checker()
        monitor = _make_monitor(expected_headers={"X-Custom": "yes"})
        success, reason = checker._evaluate_response(
            monitor,
            _make_httpx_response(headers={"X-Custom": "yes"}),
        )
        assert success
        assert reason is None

    def test_nested_json_assertion(self) -> None:
        checker = self._checker()
        monitor = _make_monitor(expected_json={"data.status": "ok"})
        success, reason = checker._evaluate_response(
            monitor,
            _make_httpx_response(json_body={"data": {"status": "ok"}}),
        )
        assert success

    def test_nested_json_mismatch(self) -> None:
        checker = self._checker()
        monitor = _make_monitor(expected_json={"data.status": "ok"})
        success, reason = checker._evaluate_response(
            monitor,
            _make_httpx_response(json_body={"data": {"status": "down"}}),
        )
        assert not success
        assert "data.status" in (reason or "")

    def test_list_index_json_assertion(self) -> None:
        checker = self._checker()
        monitor = _make_monitor(expected_json={"items.0.id": 7})
        success, _ = checker._evaluate_response(
            monitor,
            _make_httpx_response(json_body={"items": [{"id": 7}]}),
        )
        assert success


class TestRunCheckDispatch:
    async def test_heartbeat_not_pollable(self) -> None:
        from monitoring.services.checker_service import CheckerService

        checker = CheckerService()
        result = await checker.run_check(_make_monitor(monitor_type="HEARTBEAT", url=None))
        assert not result.success
        assert "push-based" in (result.error_message or "")

    async def test_tcp_dispatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from monitoring.services.checker_service import CheckerService

        writer = MagicMock()
        writer.close = MagicMock(return_value=None)
        writer.wait_closed = AsyncMock(return_value=None)

        async def fake_open_connection(host, port, **kwargs):
            return None, writer

        monkeypatch.setattr("asyncio.open_connection", fake_open_connection)
        monkeypatch.setattr(
            "monitoring.services.checker_service.validate_host_target",
            lambda target: "db.example.com",
        )

        checker = CheckerService()
        monitor = _make_monitor(monitor_type="TCP", url="tcp://db.example.com", port=5432)
        result = await checker.run_check(monitor)
        assert result.success
        assert result.meta == {"tcp_host": "db.example.com", "tcp_port": 5432}

    async def test_tcp_connection_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from monitoring.services.checker_service import CheckerService

        async def refused(host, port, **kwargs):
            raise ConnectionRefusedError("refused")

        monkeypatch.setattr("asyncio.open_connection", refused)
        monkeypatch.setattr(
            "monitoring.services.checker_service.validate_host_target",
            lambda target: "db.example.com",
        )

        checker = CheckerService()
        monitor = _make_monitor(monitor_type="TCP", url="tcp://db.example.com", port=5432)
        result = await checker.run_check(monitor)
        assert not result.success
        assert "failed" in (result.error_message or "")

    async def test_dns_dispatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import monitoring.services.checker_service as checker_module
        from monitoring.services.checker_service import CheckerService

        monkeypatch.setattr(
            checker_module,
            "_resolve_dns_records",
            lambda host, record_type, timeout: ["93.184.216.34"],
        )
        monkeypatch.setattr(
            "monitoring.services.checker_service.validate_host_target",
            lambda target: "example.com",
        )

        checker = CheckerService()
        monitor = _make_monitor(monitor_type="DNS", url="example.com", record_type="A")
        result = await checker.run_check(monitor)
        assert result.success
        assert result.meta["dns_records"] == ["93.184.216.34"]

    async def test_dns_expected_value_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import monitoring.services.checker_service as checker_module
        from monitoring.services.checker_service import CheckerService

        monkeypatch.setattr(
            checker_module,
            "_resolve_dns_records",
            lambda host, record_type, timeout: ["93.184.216.34"],
        )
        monkeypatch.setattr(
            "monitoring.services.checker_service.validate_host_target",
            lambda target: "example.com",
        )

        checker = CheckerService()
        monitor = _make_monitor(
            monitor_type="DNS",
            url="example.com",
            record_type="A",
            expected_values=["1.2.3.4"],
        )
        result = await checker.run_check(monitor)
        assert not result.success
        assert "1.2.3.4" in (result.error_message or "")

    async def test_ssl_dispatch_expired(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from monitoring.services.checker_service import CheckerService

        writer = MagicMock()
        writer.close = MagicMock(return_value=None)
        writer.wait_closed = AsyncMock(return_value=None)
        ssl_object = MagicMock()
        ssl_object.getpeercert.return_value = {
            "notAfter": "Jun  1 12:00:00 2020 GMT",  # long past
            "issuer": ((("commonName", "R11"),),),
        }
        writer.get_extra_info = MagicMock(return_value=ssl_object)

        async def fake_open_connection(host, port, **kwargs):
            return None, writer

        monkeypatch.setattr("asyncio.open_connection", fake_open_connection)
        monkeypatch.setattr(
            "monitoring.services.checker_service.validate_url_is_safe",
            lambda url: None,
        )

        checker = CheckerService()
        monitor = _make_monitor(monitor_type="SSL")
        result = await checker.run_check(monitor)
        assert not result.success
        assert "expired" in (result.error_message or "").lower()
        assert result.meta["ssl_expired"] is True

    async def test_ssl_dispatch_expiring_degraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from monitoring.services.checker_service import CheckerService

        soon = datetime.now(UTC) + timedelta(days=10)
        writer = MagicMock()
        writer.close = MagicMock(return_value=None)
        writer.wait_closed = AsyncMock(return_value=None)
        ssl_object = MagicMock()
        ssl_object.getpeercert.return_value = {
            "notAfter": soon.strftime("%b %d %H:%M:%S %Y GMT"),
            "issuer": ((("commonName", "R11"),),),
        }
        writer.get_extra_info = MagicMock(return_value=ssl_object)

        async def fake_open_connection(host, port, **kwargs):
            return None, writer

        monkeypatch.setattr("asyncio.open_connection", fake_open_connection)
        monkeypatch.setattr(
            "monitoring.services.checker_service.validate_url_is_safe",
            lambda url: None,
        )

        checker = CheckerService()
        monitor = _make_monitor(monitor_type="SSL", ssl_expiry_threshold_days=14)
        result = await checker.run_check(monitor)
        assert result.success
        assert result.meta.get("degraded") is True
        assert result.meta["ssl_issuer"] == "R11"

    async def test_ssl_verification_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from monitoring.services.checker_service import CheckerService

        async def bad_cert(host, port, **kwargs):
            raise ssl_module.SSLCertVerificationError(
                "certificate verify failed: certificate has expired",
            )

        monkeypatch.setattr("asyncio.open_connection", bad_cert)
        monkeypatch.setattr(
            "monitoring.services.checker_service.validate_url_is_safe",
            lambda url: None,
        )

        checker = CheckerService()
        monitor = _make_monitor(monitor_type="SSL")
        result = await checker.run_check(monitor)
        assert not result.success
        assert "SSL certificate validation failed" in (result.error_message or "")
