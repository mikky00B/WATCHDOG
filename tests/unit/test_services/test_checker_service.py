"""Unit tests for CheckerService — mocks all HTTP calls."""
from __future__ import annotations

import socket
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from monitoring.models.monitor import Monitor
from monitoring.services.checker_service import CheckerService


def _make_monitor(
    url: str = "https://example.com",
    timeout: float = 5.0,
    **kwargs: object,
) -> Monitor:
    m = Monitor(
        name="Test", url=url, interval_seconds=60,
        timeout_seconds=timeout, enabled=True, **kwargs,
    )
    m.id = 1
    return m


def _mock_response(
    status_code: int = 200,
    text: str = "",
    json_body: dict[str, object] | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = {}
    resp.raise_for_status = MagicMock()
    if json_body is None:
        resp.json = MagicMock(side_effect=ValueError("no json"))
    else:
        resp.json = MagicMock(return_value=json_body)
    return resp


@pytest.fixture(autouse=True)
def safe_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int,
        *args: object,
        **kwargs: object,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.unit
async def test_check_success_200() -> None:
    monitor = _make_monitor()
    checker = CheckerService()
    mock_resp = _mock_response(200)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is True
    assert result.status_code == 200
    assert result.error_message is None
    assert result.latency_ms is not None
    assert result.monitor_id == 1


@pytest.mark.unit
async def test_check_success_201() -> None:
    monitor = _make_monitor()
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(201))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is True
    assert result.status_code == 201


@pytest.mark.unit
async def test_check_failure_503() -> None:
    monitor = _make_monitor()
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(503))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is False
    assert result.status_code == 503


@pytest.mark.unit
async def test_check_timeout() -> None:
    monitor = _make_monitor()
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is False
    assert result.status_code is None
    assert result.latency_ms is None
    assert "timeout" in result.error_message.lower()


@pytest.mark.unit
async def test_check_connection_error() -> None:
    monitor = _make_monitor()
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is False
    assert result.error_message is not None
    assert result.checked_at is not None


@pytest.mark.unit
async def test_check_404_is_failure() -> None:
    monitor = _make_monitor()
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(404))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    # 4xx is a failure (not in 200-399 range)
    assert result.success is False


@pytest.mark.unit
async def test_checker_respects_semaphore() -> None:
    """Semaphore with max=1 means only 1 concurrent check."""
    checker = CheckerService(max_concurrent=1)
    assert checker.semaphore._value == 1

    checker10 = CheckerService(max_concurrent=10)
    assert checker10.semaphore._value == 10


@pytest.mark.unit
async def test_check_result_has_timestamp() -> None:
    monitor = _make_monitor()
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert isinstance(result.checked_at, datetime)


@pytest.mark.unit
async def test_unsafe_url_is_blocked_before_http_request() -> None:
    monitor = _make_monitor(url="http://127.0.0.1:8000")
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        result = await checker.check_http_endpoint(monitor)

    assert result.success is False
    assert result.status_code is None
    assert result.latency_ms is None
    assert result.error_message is not None
    assert "unsafe monitor url" in result.error_message.lower()
    mock_client_cls.assert_not_called()


@pytest.mark.unit
async def test_expected_status_code_mismatch_fails() -> None:
    monitor = _make_monitor(expected_status_code=201)
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is False
    assert result.error_message == "Expected status 201, got 200"


@pytest.mark.unit
async def test_expected_response_text_mismatch_fails() -> None:
    monitor = _make_monitor(expected_response_text="healthy")
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(200, text="down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is False
    assert result.error_message == "Expected response text was not found"


@pytest.mark.unit
async def test_expected_json_match_succeeds() -> None:
    monitor = _make_monitor(
        monitor_type="API",
        expected_json={"status": "ok"},
    )
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(200, json_body={"status": "ok"})
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is True
    assert result.error_message is None


@pytest.mark.unit
async def test_post_monitor_uses_configured_request() -> None:
    monitor = _make_monitor(
        monitor_type="API",
        http_method="POST",
        request_headers={"X-Test": "1"},
        request_body='{"ping": true}',
    )
    checker = CheckerService()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=_mock_response(200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await checker.check_http_endpoint(monitor)

    assert result.success is True
    mock_client.request.assert_awaited_once_with(
        "POST",
        "https://example.com",
        headers={"X-Test": "1"},
        content=b'{"ping": true}',
    )
