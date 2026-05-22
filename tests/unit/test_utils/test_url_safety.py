from __future__ import annotations

import socket

import pytest
from monitoring.utils.url_safety import UnsafeURLError, validate_url_is_safe


def _patch_dns(
    monkeypatch: pytest.MonkeyPatch,
    resolved_ip: str,
) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int,
        *args: object,
        **kwargs: object,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.unit
def test_allows_public_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch, "93.184.216.34")

    validate_url_is_safe("https://example.com/health")


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://0.0.0.0",
        "http://10.0.0.1",
        "http://172.16.0.1",
        "http://192.168.1.1",
        "http://169.254.169.254",
        "http://[::1]",
    ],
)
def test_blocks_internal_url_literals(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_url_is_safe(url)


@pytest.mark.unit
def test_blocks_hostnames_that_resolve_to_private_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dns(monkeypatch, "10.0.0.5")

    with pytest.raises(UnsafeURLError):
        validate_url_is_safe("https://example.com")


@pytest.mark.unit
def test_blocks_non_http_schemes() -> None:
    with pytest.raises(UnsafeURLError):
        validate_url_is_safe("file:///etc/passwd")

