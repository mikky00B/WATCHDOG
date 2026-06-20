"""Unit tests for alert channel delivery — all HTTP calls mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from monitoring.alerting.base import AlertPayload
from monitoring.alerting.email import EmailAlertChannel
from monitoring.alerting.slack import SlackAlertChannel
from monitoring.alerting.webhook import WebhookAlertChannel


def _payload(severity: str = "warning") -> AlertPayload:
    return AlertPayload(
        monitor_name="Test API",
        severity=severity,
        title="Test Alert",
        message="Something is wrong",
        timestamp="2026-01-01T00:00:00Z",
        monitor_url="https://example.com",
    )


@pytest.mark.unit
async def test_webhook_send_success() -> None:
    channel = WebhookAlertChannel("https://webhook.example.com/notify")
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await channel.send(_payload())
    assert result is True


@pytest.mark.unit
async def test_webhook_send_http_error() -> None:
    channel = WebhookAlertChannel("https://webhook.example.com/notify")
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await channel.send(_payload())
    assert result is False


@pytest.mark.unit
async def test_webhook_send_network_error() -> None:
    channel = WebhookAlertChannel("https://webhook.example.com/notify")
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("no route"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await channel.send(_payload())
    assert result is False


@pytest.mark.unit
def test_webhook_validate_valid() -> None:
    assert WebhookAlertChannel("https://example.com/hook").validate_config() is True


@pytest.mark.unit
def test_webhook_validate_empty_url() -> None:
    assert WebhookAlertChannel("").validate_config() is False


@pytest.mark.unit
async def test_webhook_invalid_config_short_circuits() -> None:
    result = await WebhookAlertChannel("").send(_payload())
    assert result is False


@pytest.mark.unit
async def test_slack_send_success() -> None:
    channel = SlackAlertChannel("https://hooks.slack.com/T000/B000/xxx")
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await channel.send(_payload("critical"))
    assert result is True


@pytest.mark.unit
async def test_slack_send_failure() -> None:
    channel = SlackAlertChannel("https://hooks.slack.com/T000/B000/xxx")
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await channel.send(_payload())
    assert result is False


@pytest.mark.unit
def test_slack_validate_config() -> None:
    assert SlackAlertChannel("https://hooks.slack.com/x").validate_config() is True
    assert SlackAlertChannel("").validate_config() is False


@pytest.mark.unit
def test_alert_payload_defaults() -> None:
    p = AlertPayload(monitor_name="X", severity="info", title="T", message="M", timestamp="now")
    assert p.monitor_url is None


@pytest.mark.unit
def test_alert_payload_with_url() -> None:
    p = AlertPayload(monitor_name="X", severity="critical", title="T", message="M",
                     timestamp="now", monitor_url="https://x.com")
    assert p.monitor_url == "https://x.com"


@pytest.mark.unit
def test_email_alert_uses_display_from_header(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, message) -> None:
            sent_messages.append(message)

    monkeypatch.setattr("monitoring.alerting.email.smtplib.SMTP", FakeSMTP)
    channel = EmailAlertChannel(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        from_email="michael@yourdomain.com",
        to_emails=["user@example.com"],
    )

    assert channel._send_sync(_payload()) is True
    assert sent_messages[0]["From"] == "Michael from Watchdog <michael@yourdomain.com>"
