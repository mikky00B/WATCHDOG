from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from monitoring.config import get_settings

settings = get_settings()

_attempts: dict[str, deque[datetime]] = defaultdict(deque)


def rate_limit_key(action: str, identifier: str) -> str:
    return f"{action}:{identifier.lower()}"


def is_rate_limited(key: str) -> bool:
    now = datetime.now(UTC)
    window_start = now - timedelta(seconds=settings.auth_rate_limit_window_seconds)
    attempts = _attempts[key]
    while attempts and attempts[0] < window_start:
        attempts.popleft()
    if len(attempts) >= settings.max_auth_attempts_per_window:
        return True
    attempts.append(now)
    return False


def clear_rate_limit(key: str) -> None:
    _attempts.pop(key, None)
