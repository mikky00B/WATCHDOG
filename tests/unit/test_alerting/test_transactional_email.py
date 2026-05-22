from __future__ import annotations

import pytest
from monitoring.alerting.transactional_email import TransactionalEmailSender


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
