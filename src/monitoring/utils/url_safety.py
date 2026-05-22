from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a monitor target URL is unsafe to request."""


BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
}

BLOCKED_IPS = {
    ipaddress.ip_address("169.254.169.254"),
}


def _is_blocked_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    return normalized in BLOCKED_HOSTNAMES or normalized.endswith(".localhost")


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address in BLOCKED_IPS
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _iter_resolved_ips(hostname: str, port: int) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    resolved: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM):
        sockaddr = item[4]
        resolved.add(ipaddress.ip_address(sockaddr[0]))
    return resolved


def validate_url_is_safe(url: str) -> None:
    """Validate that a user-supplied monitor URL is safe for outbound checks."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("Only HTTP and HTTPS monitor URLs are allowed")

    if not parsed.hostname:
        raise UnsafeURLError("Monitor URL must include a hostname")

    hostname = parsed.hostname.rstrip(".").lower()
    if _is_blocked_hostname(hostname):
        raise UnsafeURLError("Monitor URL hostname is blocked")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None:
        if _is_blocked_ip(ip):
            raise UnsafeURLError("Monitor URL resolves to a blocked IP address")
        return

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        resolved_ips = _iter_resolved_ips(hostname, port)
    except socket.gaierror as exc:
        raise UnsafeURLError("Monitor URL hostname could not be resolved") from exc

    if not resolved_ips:
        raise UnsafeURLError("Monitor URL hostname could not be resolved")

    for resolved_ip in resolved_ips:
        if _is_blocked_ip(resolved_ip):
            raise UnsafeURLError("Monitor URL resolves to a blocked IP address")

