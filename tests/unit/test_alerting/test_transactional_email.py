from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monitoring.alerting.transactional_email import TransactionalEmailSender
from monitoring.config import Settings


@pytest.mark.unit
def test_verification_email_template_is_not_monitor_alert_template() -> None:
    html = TransactionalEmailSender._html_code_body(
        heading="Verify your email",
        intro="Use this code to finish creating your WATCHDOG account.",
        code="151039",
        expires_minutes=15,
        footer="If you did not create a WATCHDOG account, you can ignore this email.",
    )
    plain = TransactionalEmailSender._plain_code_body(
        heading="Verify your email",
        intro="Use this code to finish creating your WATCHDOG account.",
        code="151039",
        expires_minutes=15,
        footer="If you did not create a WATCHDOG account, you can ignore this email.",
    )

    assert "151039" in html
    assert "Verify your email" in html
    assert "Monitor Alert" not in html
    assert "Severity" not in html
    assert "Monitor:" not in plain
    assert "Severity:" not in plain


@pytest.mark.unit
def test_password_reset_email_template_mentions_reset() -> None:
    html = TransactionalEmailSender._html_code_body(
        heading="Reset your password",
        intro="Use this code to reset your WATCHDOG password.",
        code="123456",
        expires_minutes=15,
        footer="If you did not request a password reset, you can ignore this email.",
    )

    assert "Reset your password" in html
    assert "123456" in html
    assert "Monitor Alert" not in html


@pytest.mark.unit
async def test_verification_email_sends_resend_message() -> None:
    sender = TransactionalEmailSender(
        Settings(
            _env_file=None,
            email_enabled=True,
            RESENT_API_KEY="re_test",
            from_email="sender@example.com",
        ),
        timeout=12,
    )

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        assert await sender.send_verification_code("user@example.com", "123456", 15) is True

    _, kwargs = mock_client.post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer re_test"}
    assert kwargs["json"]["to"] == ["user@example.com"]
    assert kwargs["json"]["from"] == "Michael from Watchdog <sender@example.com>"
    assert kwargs["json"]["subject"] == "Verify your WATCHDOG email"
    assert "123456" in kwargs["json"]["text"]


@pytest.mark.unit
async def test_password_reset_email_sends_resend_message() -> None:
    sender = TransactionalEmailSender(
        Settings(
            _env_file=None,
            email_enabled=True,
            RESENT_API_KEY="re_test",
            from_email="sender@example.com",
        )
    )

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        assert await sender.send_password_reset_code("user@example.com", "654321", 15) is True

    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["to"] == ["user@example.com"]
    assert kwargs["json"]["subject"] == "Reset your WATCHDOG password"
    assert "654321" in kwargs["json"]["html"]
