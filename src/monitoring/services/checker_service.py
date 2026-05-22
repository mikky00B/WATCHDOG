# monitoring/services/checker_service.py (UPDATED)
from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime

import httpx
import structlog

from monitoring.config import get_settings
from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.services.rate_limiter import RateLimiter
from monitoring.utils.url_safety import UnsafeURLError, validate_url_is_safe

logger = structlog.get_logger(__name__)
settings = get_settings()


class CheckerService:
    """Performs health checks on monitors with rate limiting and retries."""

    def __init__(
        self,
        max_concurrent: int = 100,
        requests_per_minute: int = 10,
        max_retries: int = 2,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limiter = RateLimiter(requests_per_minute)
        self.max_retries = max_retries
        self.user_agent = (
            f"MonitoringService/1.0 (+{settings.contact_email or 'monitoring'})"
        )

    async def check_http_endpoint(
        self,
        monitor: Monitor,
        retry_count: int = 0,
    ) -> CheckResult:
        """
        Perform HTTP endpoint check with rate limiting and retry logic.

        Args:
            monitor: Monitor to check
            retry_count: Current retry attempt (internal use)

        Returns:
            CheckResult with check outcome
        """
        async with self.semaphore:
            if monitor.url is None:
                return CheckResult(
                    monitor_id=monitor.id,
                    status_code=None,
                    latency_ms=None,
                    success=False,
                    error_message="Monitor URL is required for HTTP checks",
                    checked_at=datetime.now(UTC),
                )

            try:
                validate_url_is_safe(monitor.url)
            except UnsafeURLError as exc:
                logger.warning(
                    "unsafe_monitor_url_blocked",
                    monitor_id=monitor.id,
                    url=monitor.url,
                    reason=str(exc),
                )
                return CheckResult(
                    monitor_id=monitor.id,
                    status_code=None,
                    latency_ms=None,
                    success=False,
                    error_message=f"Unsafe monitor URL: {str(exc)}",
                    checked_at=datetime.now(UTC),
                )

            # Apply rate limiting per domain
            await self.rate_limiter.acquire(monitor.url)

            logger.info(
                "http_check_start",
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                url=monitor.url,
                retry=retry_count,
            )

            start_time = asyncio.get_event_loop().time()

            try:
                async with httpx.AsyncClient(
                    timeout=monitor.timeout_seconds,
                    follow_redirects=False,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "*/*",
                    },
                ) as client:
                    response = await self._send_request(client, monitor)

                    elapsed = asyncio.get_event_loop().time() - start_time
                    latency_ms = elapsed * 1000

                    # Handle rate limiting from server
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(
                            "server_rate_limited",
                            monitor_id=monitor.id,
                            retry_after=retry_after,
                        )

                        # Don't retry immediately, mark as failed
                        # Next scheduled check will try again
                        return CheckResult(
                            monitor_id=monitor.id,
                            status_code=response.status_code,
                            latency_ms=latency_ms,
                            success=False,
                            error_message=f"Rate limited by server (retry after {retry_after}s)",
                            checked_at=datetime.now(UTC),
                        )

                    success, failure_reason = self._evaluate_response(monitor, response)

                    logger.info(
                        "http_check_complete",
                        monitor_id=monitor.id,
                        status_code=response.status_code,
                        latency_ms=round(latency_ms, 2),
                        success=success,
                    )

                    return CheckResult(
                        monitor_id=monitor.id,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        success=success,
                        error_message=failure_reason,
                        checked_at=datetime.now(UTC),
                    )

            except httpx.TimeoutException:
                logger.warning(
                    "http_check_timeout",
                    monitor_id=monitor.id,
                    timeout=monitor.timeout_seconds,
                    retry=retry_count,
                )

                # Retry on timeout
                if retry_count < self.max_retries:
                    backoff = 2**retry_count + random.uniform(0, 1)
                    logger.info(
                        "retrying_after_timeout",
                        monitor_id=monitor.id,
                        backoff_seconds=round(backoff, 2),
                    )
                    await asyncio.sleep(backoff)
                    return await self.check_http_endpoint(monitor, retry_count + 1)

                return CheckResult(
                    monitor_id=monitor.id,
                    status_code=None,
                    latency_ms=None,
                    success=False,
                    error_message="Request timeout",
                    checked_at=datetime.now(UTC),
                )

            except httpx.RequestError as exc:
                logger.error(
                    "http_check_error",
                    monitor_id=monitor.id,
                    error=str(exc),
                    retry=retry_count,
                )

                # Retry on network errors
                if retry_count < self.max_retries:
                    backoff = 2**retry_count + random.uniform(0, 1)
                    logger.info(
                        "retrying_after_error",
                        monitor_id=monitor.id,
                        backoff_seconds=round(backoff, 2),
                    )
                    await asyncio.sleep(backoff)
                    return await self.check_http_endpoint(monitor, retry_count + 1)

                return CheckResult(
                    monitor_id=monitor.id,
                    status_code=None,
                    latency_ms=None,
                    success=False,
                    error_message=str(exc),
                    checked_at=datetime.now(UTC),
                )

            except Exception as exc:
                # Catch-all for unexpected errors
                logger.error(
                    "http_check_unexpected_error",
                    monitor_id=monitor.id,
                    error=str(exc),
                    exc_info=True,
                )
                return CheckResult(
                    monitor_id=monitor.id,
                    status_code=None,
                    latency_ms=None,
                    success=False,
                    error_message=f"Unexpected error: {str(exc)}",
                    checked_at=datetime.now(UTC),
                )

    async def _send_request(
        self,
        client: httpx.AsyncClient,
        monitor: Monitor,
    ) -> httpx.Response:
        method = (monitor.http_method or "GET").upper()
        headers = monitor.request_headers or None

        if method == "GET" and headers is None and monitor.request_body is None:
            return await client.get(monitor.url)

        content = monitor.request_body.encode() if monitor.request_body is not None else None
        return await client.request(
            method,
            monitor.url,
            headers=headers,
            content=content,
        )

    def _evaluate_response(
        self,
        monitor: Monitor,
        response: httpx.Response,
    ) -> tuple[bool, str | None]:
        expected_status = monitor.expected_status_code
        if expected_status is not None and response.status_code != expected_status:
            return (
                False,
                f"Expected status {expected_status}, got {response.status_code}",
            )
        elif not 200 <= response.status_code < 400:
            return False, None

        if (
            monitor.expected_response_text
            and monitor.expected_response_text not in response.text
        ):
            return False, "Expected response text was not found"

        if monitor.expected_json:
            try:
                body = response.json()
            except (ValueError, json.JSONDecodeError):
                return False, "Response body is not valid JSON"

            if not isinstance(body, dict):
                return False, "Response JSON must be an object"

            for key, expected_value in monitor.expected_json.items():
                if body.get(key) != expected_value:
                    return False, f"Expected JSON {key}={expected_value!r}"

        return True, None
