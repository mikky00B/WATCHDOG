# monitoring/services/checker_service.py
from __future__ import annotations

import asyncio
import json
import random
import ssl as ssl_module
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import dns.exception
import dns.resolver
import httpx
import structlog

from monitoring.config import get_settings
from monitoring.models.check_result import CheckResult
from monitoring.models.monitor import Monitor
from monitoring.services.rate_limiter import RateLimiter
from monitoring.utils.url_safety import (
    UnsafeURLError,
    validate_host_target,
    validate_url_is_safe,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

DEFAULT_SSL_EXPIRY_THRESHOLD_DAYS = 14


class CheckerService:
    """Performs health checks on monitors with rate limiting and retries.

    Supports WEBSITE/API (HTTP), SSL (certificate expiry), DNS (record
    resolution), TCP (port connectivity), and HEARTBEAT (push-based, never
    polled) monitor types via :meth:`run_check`.
    """

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

    async def run_check(self, monitor: Monitor) -> CheckResult:
        """Dispatch a check to the executor matching the monitor type."""
        monitor_type = (monitor.monitor_type or "http").upper()
        if monitor_type in {"WEBSITE", "API", "HTTP"}:
            return await self.check_http_endpoint(monitor)
        if monitor_type == "SSL":
            return await self.check_ssl_certificate(monitor)
        if monitor_type == "DNS":
            return await self.check_dns_record(monitor)
        if monitor_type == "TCP":
            return await self.check_tcp_port(monitor)
        return self._failed_result(
            monitor,
            f"Monitor type '{monitor.monitor_type}' is not executable (heartbeat "
            "monitors are push-based)",
        )

    def _failed_result(self, monitor: Monitor, error_message: str) -> CheckResult:
        return CheckResult(
            monitor_id=monitor.id,
            status_code=None,
            latency_ms=None,
            success=False,
            error_message=error_message,
            checked_at=datetime.now(UTC),
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
                return self._failed_result(monitor, "Monitor URL is required for HTTP checks")

            try:
                validate_url_is_safe(monitor.url)
            except UnsafeURLError as exc:
                logger.warning(
                    "unsafe_monitor_url_blocked",
                    monitor_id=monitor.id,
                    url=monitor.url,
                    reason=str(exc),
                )
                return self._failed_result(monitor, f"Unsafe monitor URL: {str(exc)}")

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

                    # Enforce the per-monitor response time budget.
                    if (
                        success
                        and monitor.response_time_threshold_ms is not None
                        and latency_ms > monitor.response_time_threshold_ms
                    ):
                        success = False
                        failure_reason = (
                            f"Response time {round(latency_ms)}ms exceeded threshold "
                            f"{monitor.response_time_threshold_ms}ms"
                        )

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

                return self._failed_result(monitor, "Request timeout")

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

                return self._failed_result(monitor, str(exc))

            except Exception as exc:
                # Catch-all for unexpected errors
                logger.error(
                    "http_check_unexpected_error",
                    monitor_id=monitor.id,
                    error=str(exc),
                    exc_info=True,
                )
                return self._failed_result(monitor, f"Unexpected error: {str(exc)}")

    async def check_ssl_certificate(self, monitor: Monitor) -> CheckResult:
        """Inspect the TLS certificate of the monitor target.

        Fails on invalid/expired certificates; reports DEGRADED via the check
        metadata when the certificate expires within the configured threshold.
        """
        async with self.semaphore:
            if monitor.url is None:
                return self._failed_result(monitor, "Monitor URL is required for SSL checks")

            parsed = urlparse(monitor.url)
            host = parsed.hostname
            if not host:
                return self._failed_result(monitor, "Monitor URL must include a hostname")
            port = monitor.port or parsed.port or 443

            try:
                validate_url_is_safe(monitor.url)
            except UnsafeURLError as exc:
                return self._failed_result(monitor, f"Unsafe monitor URL: {str(exc)}")

            start_time = asyncio.get_event_loop().time()
            ssl_context = ssl_module.create_default_context()

            try:
                _reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port, ssl=ssl_context),
                    timeout=monitor.timeout_seconds,
                )
                try:
                    ssl_object = writer.get_extra_info("ssl_object")
                    cert = ssl_object.getpeercert() if ssl_object else None
                finally:
                    writer.close()
                    await writer.wait_closed()
            except ssl_module.SSLCertVerificationError as exc:
                logger.warning(
                    "ssl_certificate_invalid",
                    monitor_id=monitor.id,
                    host=host,
                    error=str(exc),
                )
                return self._failed_result(
                    monitor,
                    "SSL certificate validation failed: "
                    f"{getattr(exc, 'verify_message', None) or str(exc)}",
                )
            except (ssl_module.SSLError, OSError, ValueError) as exc:
                logger.warning(
                    "ssl_check_error",
                    monitor_id=monitor.id,
                    host=host,
                    error=str(exc),
                )
                return self._failed_result(monitor, f"SSL connection failed: {str(exc)}")
            except asyncio.TimeoutError:
                return self._failed_result(monitor, "SSL check timed out")

            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            if not cert or "notAfter" not in cert:
                return self._failed_result(monitor, "SSL certificate could not be read")

            now = datetime.now(UTC)
            expires_at = _parse_cert_date(cert["notAfter"])
            days_remaining = (expires_at - now).total_seconds() / 86400
            threshold_days = monitor.ssl_expiry_threshold_days or DEFAULT_SSL_EXPIRY_THRESHOLD_DAYS
            issuer = _cert_issuer_common_name(cert)

            meta: dict[str, object] = {
                "ssl_expires_at": expires_at.isoformat(),
                "ssl_issuer": issuer,
                "ssl_days_remaining": round(days_remaining, 1),
            }

            if expires_at <= now:
                meta["ssl_expired"] = True
                return CheckResult(
                    monitor_id=monitor.id,
                    status_code=None,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=(
                        f"SSL certificate expired on {expires_at.strftime('%Y-%m-%d')}"
                    ),
                    meta=meta,
                    checked_at=datetime.now(UTC),
                )

            if days_remaining <= threshold_days:
                meta["degraded"] = True
                meta["warning"] = (
                    f"SSL certificate expires in {round(days_remaining)} days "
                    f"({expires_at.strftime('%Y-%m-%d')})"
                )
                logger.warning(
                    "ssl_certificate_expiring",
                    monitor_id=monitor.id,
                    days_remaining=round(days_remaining),
                )

            logger.info(
                "ssl_check_complete",
                monitor_id=monitor.id,
                days_remaining=round(days_remaining, 1),
                degraded=bool(meta.get("degraded")),
            )
            return CheckResult(
                monitor_id=monitor.id,
                status_code=None,
                latency_ms=latency_ms,
                success=True,
                error_message=None,
                meta=meta,
                checked_at=datetime.now(UTC),
            )

    async def check_dns_record(self, monitor: Monitor) -> CheckResult:
        """Resolve the monitor's DNS record type and verify expected values."""
        async with self.semaphore:
            if monitor.url is None:
                return self._failed_result(monitor, "Monitor target is required for DNS checks")

            try:
                host = validate_host_target(monitor.url)
            except UnsafeURLError as exc:
                return self._failed_result(monitor, f"Unsafe monitor target: {str(exc)}")

            record_type = (monitor.record_type or "A").upper()
            start_time = asyncio.get_event_loop().time()

            try:
                values = await asyncio.to_thread(
                    _resolve_dns_records,
                    host,
                    record_type,
                    monitor.timeout_seconds,
                )
            except dns.resolver.NXDOMAIN:
                logger.info(
                    "dns_check_failed",
                    monitor_id=monitor.id,
                    host=host,
                    record_type=record_type,
                    error="domain does not exist",
                )
                return self._failed_result(
                    monitor,
                    f"DNS {record_type} lookup failed: domain does not exist",
                )
            except dns.resolver.NoAnswer:
                return self._failed_result(
                    monitor,
                    f"DNS {record_type} lookup failed: no {record_type} records found",
                )
            except (dns.exception.DNSException, OSError) as exc:
                logger.info(
                    "dns_check_failed",
                    monitor_id=monitor.id,
                    host=host,
                    record_type=record_type,
                    error=str(exc),
                )
                return self._failed_result(
                    monitor,
                    f"DNS {record_type} lookup failed: {str(exc) or type(exc).__name__}",
                )

            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            meta: dict[str, object] = {"dns_records": values, "record_type": record_type}

            if monitor.expected_values:
                expected = {str(value).strip().rstrip(".") for value in monitor.expected_values}
                found = {value.rstrip(".") for value in values}
                missing = expected - found
                if missing:
                    return CheckResult(
                        monitor_id=monitor.id,
                        status_code=None,
                        latency_ms=latency_ms,
                        success=False,
                        error_message=(
                            f"Expected {record_type} value(s) not found: "
                            f"{', '.join(sorted(missing))}"
                        ),
                        meta=meta,
                        checked_at=datetime.now(UTC),
                    )

            logger.info(
                "dns_check_complete",
                monitor_id=monitor.id,
                host=host,
                record_type=record_type,
                record_count=len(values),
            )
            return CheckResult(
                monitor_id=monitor.id,
                status_code=None,
                latency_ms=latency_ms,
                success=True,
                error_message=None,
                meta=meta,
                checked_at=datetime.now(UTC),
            )

    async def check_tcp_port(self, monitor: Monitor) -> CheckResult:
        """Open a TCP connection to the monitor's host and port."""
        async with self.semaphore:
            if monitor.url is None:
                return self._failed_result(monitor, "Monitor target is required for TCP checks")

            try:
                host = validate_host_target(monitor.url)
            except UnsafeURLError as exc:
                return self._failed_result(monitor, f"Unsafe monitor target: {str(exc)}")

            parsed = urlparse(monitor.url)
            port = monitor.port or parsed.port
            if port is None:
                return self._failed_result(monitor, "TCP monitors require a port")

            start_time = asyncio.get_event_loop().time()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=monitor.timeout_seconds,
                )
                writer.close()
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError) as exc:
                message = "TCP connection timed out" if isinstance(exc, asyncio.TimeoutError) else str(exc)
                logger.info(
                    "tcp_check_failed",
                    monitor_id=monitor.id,
                    host=host,
                    port=port,
                    error=message,
                )
                return CheckResult(
                    monitor_id=monitor.id,
                    status_code=None,
                    latency_ms=None,
                    success=False,
                    error_message=f"TCP connect to {host}:{port} failed: {message}",
                    meta={"tcp_host": host, "tcp_port": port},
                    checked_at=datetime.now(UTC),
                )

            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.info(
                "tcp_check_complete",
                monitor_id=monitor.id,
                host=host,
                port=port,
                latency_ms=round(latency_ms, 2),
            )
            return CheckResult(
                monitor_id=monitor.id,
                status_code=None,
                latency_ms=latency_ms,
                success=True,
                error_message=None,
                meta={"tcp_host": host, "tcp_port": port},
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

        if monitor.expected_headers:
            for header_name, expected_value in monitor.expected_headers.items():
                actual = response.headers.get(header_name)
                if actual is None:
                    return False, f"Expected response header '{header_name}' is missing"
                if actual.strip() != str(expected_value).strip():
                    return (
                        False,
                        f"Expected header {header_name}={expected_value!r}, "
                        f"got {actual!r}",
                    )

        if monitor.expected_json:
            try:
                body = response.json()
            except (ValueError, json.JSONDecodeError):
                return False, "Response body is not valid JSON"

            for key, expected_value in monitor.expected_json.items():
                try:
                    actual_value = _extract_json_path(body, key)
                except KeyError:
                    return False, f"Expected JSON key '{key}' is missing"
                if actual_value != expected_value:
                    return False, f"Expected JSON {key}={expected_value!r}"

        return True, None


def _resolve_dns_records(host: str, record_type: str, timeout_seconds: float) -> list[str]:
    """Blocking DNS resolution executed in a worker thread."""
    resolver = dns.resolver.Resolver(configure=True)
    resolver.lifetime = timeout_seconds
    resolver.timeout = timeout_seconds
    answers = resolver.resolve(host, record_type)
    values: list[str] = []
    for answer in answers:
        text = answer.to_text().strip().rstrip(".")
        # TXT records render with surrounding quotes ("v=spf1 ...") — strip
        # them so expected-value comparisons match user input.
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            text = text[1:-1]
        values.append(text)
    return values


def _parse_cert_date(value: str) -> datetime:
    """Parse an X.509 notBefore/notAfter date ('Jun  1 12:00:00 2026 GMT')."""
    parsed = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z")
    return parsed.replace(tzinfo=UTC)


def _cert_issuer_common_name(cert: dict[str, object]) -> str:
    """Extract a readable issuer name from a getpeercert() dict."""
    issuer = cert.get("issuer") or ()
    for rdn in issuer:
        for key, value in rdn:
            if key == "commonName":
                return str(value)
    return "unknown"


def _extract_json_path(body: object, path: str) -> object:
    """Resolve a dotted path like 'data.items.0.status' against a JSON body."""
    if "." not in path:
        if not isinstance(body, dict) or path not in body:
            raise KeyError(path)
        return body[path]

    current: object = body
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(path)
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
                current = current[index]
            except (ValueError, IndexError) as exc:
                raise KeyError(path) from exc
        else:
            raise KeyError(path)
    return current


def apply_check_result_to_monitor(monitor: Monitor, result: CheckResult) -> None:
    """Copy type-specific check metadata onto the monitor record.

    Currently updates SSL certificate tracking fields (expiry, issuer) and
    keeps the monitor's DEGRADED status in sync with SSL warnings.
    """
    meta = result.meta or {}
    if meta.get("ssl_expires_at"):
        try:
            monitor.ssl_expires_at = datetime.fromisoformat(str(meta["ssl_expires_at"]))
        except ValueError:
            logger.warning(
                "ssl_meta_parse_failed",
                monitor_id=monitor.id,
                value=str(meta.get("ssl_expires_at")),
            )
    if meta.get("ssl_issuer"):
        monitor.ssl_issuer = str(meta["ssl_issuer"])
    if meta.get("ssl_expires_at") and meta.get("ssl_days_remaining") is not None:
        days_remaining = float(meta["ssl_days_remaining"])  # type: ignore[arg-type]
        threshold_days = monitor.ssl_expiry_threshold_days or DEFAULT_SSL_EXPIRY_THRESHOLD_DAYS
        if days_remaining <= 0:
            monitor.status = "DOWN"
        elif days_remaining <= threshold_days:
            monitor.status = "DEGRADED"


def ssl_expiry_deadline(days: int) -> datetime:
    """Helper used by tests to compute threshold boundaries."""
    return datetime.now(UTC) + timedelta(days=days)
