from __future__ import annotations

from email.utils import formataddr


DEFAULT_FROM_NAME = "Michael from Watchdog"


def format_from_address(email_address: str, display_name: str = DEFAULT_FROM_NAME) -> str:
    """Build a From header value while keeping the envelope mailbox configurable."""
    return formataddr((display_name, email_address))
