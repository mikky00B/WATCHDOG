"""Tests for log redaction and period parsing utilities."""

from __future__ import annotations

import pytest
from monitoring.utils.redaction import redact_attributes, redact_text
from monitoring.utils.time_period import InvalidPeriodError, bucket_seconds_for, parse_period


class TestRedactText:
    def test_bearer_token_redacted(self) -> None:
        text = "Authorization=Bearer abcdef1234567890abcdef done"
        redacted = redact_text(text)
        assert "abcdef1234567890" not in redacted
        assert "[REDACTED]" in redacted
        assert "Bearer" in redacted  # prefix kept for context

    def test_jwt_redacted(self) -> None:
        text = "token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c"
        assert "eyJhbGciOiJIUzI1NiIs" not in redact_text(text)

    def test_key_value_secret_redacted(self) -> None:
        redacted = redact_text("password: hunter2secret")
        assert "hunter2secret" not in redacted

    def test_card_number_redacted(self) -> None:
        redacted = redact_text("card 4111 1111 1111 1111 charged")
        assert "4111" not in redacted

    def test_normal_text_untouched(self) -> None:
        assert redact_text("User michael logged in from 10.0.0.1") == (
            "User michael logged in from 10.0.0.1"
        )


class TestRedactAttributes:
    def test_sensitive_keys_redacted(self) -> None:
        redacted = redact_attributes({"password": "hunter2", "api_key": "xyz", "user": "michael"})
        assert redacted["password"] == "[REDACTED]"
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["user"] == "michael"

    def test_string_values_redacted(self) -> None:
        redacted = redact_attributes({"note": "Bearer abcdef1234567890abcdef"})
        assert "abcdef1234567890" not in redacted["note"]

    def test_nested_dicts_redacted(self) -> None:
        redacted = redact_attributes({"payload": {"token": "secret-token-value"}})
        assert redacted["payload"]["token"] == "[REDACTED]"

    def test_non_string_values_kept(self) -> None:
        redacted = redact_attributes({"count": 5, "enabled": True})
        assert redacted["count"] == 5
        assert redacted["enabled"] is True


class TestParsePeriod:
    def test_hours(self) -> None:
        assert parse_period("24h") == 24.0

    def test_days(self) -> None:
        assert parse_period("7d") == 24.0 * 7

    def test_weeks(self) -> None:
        assert parse_period("2w") == 24.0 * 14

    def test_minutes(self) -> None:
        assert parse_period("30m") == 0.5

    def test_empty_uses_default(self) -> None:
        assert parse_period("") == 24.0
        assert parse_period("", default="1h") == 1.0

    def test_invalid_raises(self) -> None:
        with pytest.raises(InvalidPeriodError):
            parse_period("banana")

    def test_bucket_seconds_scale(self) -> None:
        assert bucket_seconds_for(0.5) == 300
        assert bucket_seconds_for(3) == 900
        assert bucket_seconds_for(24) == 3600
        assert bucket_seconds_for(24 * 30) == 24 * 3600
