# monitoring/services/rate_limiter.py
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)


class RateLimiter:
    """Rate limiter to prevent overwhelming target sites."""

    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self.site_requests: Dict[str, list[datetime]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL for rate limiting."""
        parsed = urlparse(url)
        return parsed.netloc or url

    async def acquire(self, url: str):
        """Wait if necessary to respect rate limits for a site."""
        domain = self._get_domain(url)

        async with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(minutes=1)

            # Remove old requests
            self.site_requests[domain] = [
                ts for ts in self.site_requests[domain] if ts > cutoff
            ]

            # Check if we need to wait
            if len(self.site_requests[domain]) >= self.requests_per_minute:
                oldest = self.site_requests[domain][0]
                wait_time = (oldest + timedelta(minutes=1) - now).total_seconds()
                if wait_time > 0:
                    logger.info(
                        "rate_limit_wait",
                        domain=domain,
                        wait_seconds=round(wait_time, 2),
                    )
                    await asyncio.sleep(wait_time)

            # Record this request
            self.site_requests[domain].append(now)
