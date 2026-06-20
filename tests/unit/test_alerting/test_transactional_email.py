from __future__ import annotations

import pytest
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
async def test_verification_email_sends_smtp_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_messages = []
    connections = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.login_args = None
            connections.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self) -> None:
            self.started_tls = True

        def login(self, user: str, password: str) -> None:
            self.login_args = (user, password)

        def send_message(self, message) -> None:
            sent_messages.append(message)

    monkeypatch.setattr("monitoring.alerting.transactional_email.smtplib.SMTP", FakeSMTP)

    sender = TransactionalEmailSender(
        Settings(
            _env_file=None,
            email_enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="sender@example.com",
            smtp_password="secret",
            from_email="sender@example.com",
        ),
        timeout=12,
    )

    assert await sender.send_verification_code("user@example.com", "123456", 15) is True

    assert len(connections) == 1
    assert connections[0].host == "smtp.example.com"
    assert connections[0].port == 587
    assert connections[0].timeout == 12
    assert connections[0].started_tls is True
    assert connections[0].login_args == ("sender@example.com", "secret")
    assert sent_messages[0]["To"] == "user@example.com"
    assert sent_messages[0]["From"] == "Michael from Watchdog <sender@example.com>"
    assert sent_messages[0]["Subject"] == "Verify your WATCHDOG email"


@pytest.mark.unit
async def test_password_reset_email_sends_smtp_ssl_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_messages = []
    connections = []

    class FakeSMTPSSL:
        def __init__(self, host: str, port: int, timeout: int):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.login_args = None
            connections.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self) -> None:
            self.started_tls = True

        def login(self, user: str, password: str) -> None:
            self.login_args = (user, password)

        def send_message(self, message) -> None:
            sent_messages.append(message)

    monkeypatch.setattr("monitoring.alerting.transactional_email.smtplib.SMTP_SSL", FakeSMTPSSL)

    sender = TransactionalEmailSender(
        Settings(
            _env_file=None,
            email_enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_user="sender@example.com",
            smtp_password="secret",
            from_email="sender@example.com",
        )
    )

    assert await sender.send_password_reset_code("user@example.com", "654321", 15) is True

    assert connections[0].host == "smtp.example.com"
    assert connections[0].port == 465
    assert connections[0].started_tls is False
    assert connections[0].login_args == ("sender@example.com", "secret")
    assert sent_messages[0]["To"] == "user@example.com"
    assert sent_messages[0]["Subject"] == "Reset your WATCHDOG password"
