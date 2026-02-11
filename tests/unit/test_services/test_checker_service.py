"""Unit tests for CheckerService — mocks all HTTP calls."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from monitoring.models.monitor import Monitor
from monitoring.services.checker_service import CheckerService


def _make_monitor(url: str = "https://example.com", timeout: float = 5.0) -> Monitor:
    m = Monitor(
        name="Test", url=url, interval_seconds=60,
        timeout_seconds=timeout, enabled=True,
    )
    m.id = 1
    return m


def _mock_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


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
