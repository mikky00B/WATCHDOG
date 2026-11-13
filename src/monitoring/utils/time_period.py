from __future__ import annotations

import re

__all__ = ["parse_period"]


_PERIOD_PATTERN = re.compile(r"^(\d+)([smhdw])$")
_UNIT_HOURS = {
    "s": 1 / 3600,
    "m": 1 / 60,
    "h": 1.0,
    "d": 24.0,
    "w": 24.0 * 7,
}


class InvalidPeriodError(ValueError):
    """Raised when a period string cannot be parsed."""


def parse_period(period: str, default: str = "24h") -> float:
    """Parse a period like '30m', '24h', '7d', '2w' into hours (float)."""
    if not period:
        period = default
    match = _PERIOD_PATTERN.match(period.strip().lower())
    if match is None:
        raise InvalidPeriodError(
            f"Invalid period '{period}'. Use forms like 30m, 12h, 7d, 2w.",
        )
    value, unit = match.groups()
    return int(value) * _UNIT_HOURS[unit]


def bucket_seconds_for(hours: float) -> int:
    """Pick a bucket size (seconds) that yields a readable number of buckets."""
    if hours <= 1:
        return 300  # 5 min
    if hours <= 6:
        return 900  # 15 min
    if hours <= 48:
        return 3600  # hourly
    if hours <= 24 * 14:
        return 6 * 3600
    return 24 * 3600  # daily
