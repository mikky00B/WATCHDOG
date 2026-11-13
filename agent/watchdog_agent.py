#!/usr/bin/env python3
"""WATCHDOG infrastructure monitoring agent.

A lightweight, dependency-minimal agent that collects host metrics (CPU, RAM,
disk, network utilization, top processes, watched services) and pushes them to
the WATCHDOG ingestion API.

Requirements:
    Python 3.8+ and `psutil` (`pip install psutil`). Everything else is stdlib.

Usage:
    python watchdog_agent.py \
        --api-url https://watchdog.example.com/api/v1 \
        --api-key wd_live_XXXXXXXX \
        --interval 60 \
        --watch nginx,postgres \
        --host web-01

    Values may also be provided via environment variables:
        WATCHDOG_API_URL, WATCHDOG_API_KEY, WATCHDOG_INTERVAL,
        WATCHDOG_HOST, WATCHDOG_WATCH, WATCHDOG_ENVIRONMENT

Exit codes: 0 on clean shutdown, 1 on configuration errors.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

DEFAULT_INTERVAL = 60
DEFAULT_API_URL = "http://localhost:8000/api/v1"
MAX_TOP_PROCESSES = 8


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def log(message: str) -> None:
    print(f"{utc_now_iso()} {message}", flush=True)


def collect_metrics(previous_net: dict[str, tuple[int, int]] | None, interval: float) -> tuple[dict, dict[str, tuple[int, int]]]:
    """Collect one metrics sample. Returns (payload, net_counters_for_next_delta)."""
    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net_io = psutil.net_io_counters()

    sent_delta = max(0, net_io.bytes_sent - (previous_net or {}).get("sent", net_io.bytes_sent))
    recv_delta = max(0, net_io.bytes_recv - (previous_net or {}).get("recv", net_io.bytes_recv))
    elapsed = max(interval, 1.0)
    net_in_kb_per_s = (recv_delta / 1024) / elapsed
    net_out_kb_per_s = (sent_delta / 1024) / elapsed

    processes = []
    for proc in sorted(
        psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
        key=lambda p: (p.info.get("cpu_percent") or 0),
        reverse=True,
    )[:MAX_TOP_PROCESSES]:
        try:
            processes.append(
                {
                    "pid": proc.info.get("pid"),
                    "name": (proc.info.get("name") or "")[:255],
                    "cpu": proc.info.get("cpu_percent"),
                    "memory": proc.info.get("memory_percent"),
                },
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    payload = {
        "host": HOSTNAME,
        "timestamp": utc_now_iso(),
        "cpu_percent": round(cpu_percent, 1),
        "memory_percent": round(memory.percent, 1),
        "memory_used_mb": round((memory.total - memory.available) / (1024 * 1024), 1),
        "disk_percent": round(disk.percent, 1),
        "disk_used_gb": round(disk.used / (1024 * 1024 * 1024), 2),
        "net_in_kb_per_s": round(net_in_kb_per_s, 2),
        "net_out_kb_per_s": round(net_out_kb_per_s, 2),
        "processes": processes,
    }
    if WATCHED_SERVICES:
        payload["service_checks"] = check_services(WATCHED_SERVICES)
    if ENVIRONMENT:
        payload["environment"] = ENVIRONMENT

    counters = {"sent": net_io.bytes_sent, "recv": net_io.bytes_recv}
    return payload, counters


def check_services(watched: list[str]) -> dict[str, bool]:
    """Return {name: running} for each watched process name."""
    running: dict[str, bool] = {name: False for name in watched}
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        for watched_name in watched:
            if not running[watched_name] and watched_name.lower() in name:
                running[watched_name] = True
    return running


def post_metrics(api_url: str, api_key: str, payload: dict) -> tuple[int, str]:
    """POST one metrics sample. Returns (status_code, body)."""
    url = api_url.rstrip("/") + "/infrastructure/ingest"
    body = json.dumps({"metrics": [payload]}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "User-Agent": "watchdog-agent/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WATCHDOG infrastructure agent")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("WATCHDOG_API_URL", DEFAULT_API_URL),
        help="WATCHDOG API base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("WATCHDOG_API_KEY", ""),
        help="WATCHDOG API key (wd_live_...)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("WATCHDOG_INTERVAL", str(DEFAULT_INTERVAL))),
        help="Sampling interval in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("WATCHDOG_HOST", socket.gethostname()),
        help="Host label reported to WATCHDOG (default: machine hostname)",
    )
    parser.add_argument(
        "--watch",
        default=os.environ.get("WATCHDOG_WATCH", ""),
        help="Comma-separated process names to monitor (e.g. nginx,postgres)",
    )
    parser.add_argument(
        "--environment",
        default=os.environ.get("WATCHDOG_ENVIRONMENT", ""),
        help="Environment label (e.g. production)",
    )
    return parser.parse_args()


def main() -> int:
    global HOSTNAME, WATCHED_SERVICES, ENVIRONMENT

    if psutil is None:
        log("ERROR: psutil is required. Install it with: pip install psutil")
        return 1

    args = parse_args()
    if not args.api_key:
        log("ERROR: an API key is required (--api-key or WATCHDOG_API_KEY)")
        return 1
    if args.interval < 10:
        log("ERROR: interval must be at least 10 seconds")
        return 1

    HOSTNAME = args.host
    ENVIRONMENT = args.environment or None
    WATCHED_SERVICES = [name.strip() for name in args.watch.split(",") if name.strip()]

    log(f"watchdog agent starting: host={HOSTNAME} interval={args.interval}s url={args.api_url}")
    if WATCHED_SERVICES:
        log(f"watching services: {', '.join(WATCHED_SERVICES)}")

    # Prime psutil's cpu_percent baseline.
    psutil.cpu_percent(interval=None)
    previous_net: dict[str, tuple[int, int]] | None = None

    while True:
        started = time.monotonic()
        try:
            payload, previous_net = collect_metrics(previous_net, args.interval)
            status, body = post_metrics(args.api_url, args.api_key, payload)
            if status in (200, 202):
                log(
                    "metrics sent: cpu={cpu_percent}% mem={memory_percent}% "
                    "disk={disk_percent}% in={net_in_kb_per_s}KB/s out={net_out_kb_per_s}KB/s".format(
                        **payload,
                    ),
                )
            else:
                log(f"ERROR: ingest failed with HTTP {status}: {body[:300]}")
        except Exception as exc:  # noqa: BLE001 — agent must never crash on one bad cycle
            log(f"ERROR: metrics collection failed: {exc}")

        elapsed = time.monotonic() - started
        sleep_for = max(1.0, args.interval - elapsed)
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            log("agent stopping")
            return 0


if __name__ == "__main__":
    HOSTNAME = socket.gethostname()
    WATCHED_SERVICES: list[str] = []
    ENVIRONMENT: str | None = None
    sys.exit(main())
