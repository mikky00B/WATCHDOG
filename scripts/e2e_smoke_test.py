"""One-off end-to-end smoke test for the observability expansion.

Run against a local API booted with a disposable database:
    python scripts/e2e_smoke_test.py
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg
import httpx

BASE = "http://127.0.0.1:8766/api/v1"
DB = "postgresql://postgres:Clevermike@127.0.0.1:5433/watchdog_e2e"


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        # 1. Register + force-verify via direct DB + login
        r = await c.post(
            f"{BASE}/auth/register",
            json={"full_name": "E2E", "email": "e2e@test.dev", "password": "StrongPass123"},
        )
        assert r.status_code == 201, r.text
        conn = await asyncpg.connect(DB)
        await conn.execute("UPDATE users SET is_verified = true WHERE email = 'e2e@test.dev'")
        await conn.close()
        r = await c.post(
            f"{BASE}/auth/login",
            json={"email": "e2e@test.dev", "password": "StrongPass123"},
        )
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Org
        r = await c.post(
            f"{BASE}/organizations/",
            json={"name": "E2E Org", "slug": "e2e-org"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        org_id = r.json()["public_id"]

        # 3. API key
        r = await c.post(
            f"{BASE}/api-keys/",
            json={"organization_id": org_id, "name": "agent key"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        key = r.json()["key"]
        key_headers = {"X-API-Key": key}
        print("api key created:", key[:12] + "...")

        # 4. Log ingestion (with secret material to verify redaction)
        logs = {
            "logs": [
                {
                    "application": "checkout-api",
                    "level": "ERROR",
                    "message": "Payment failed: Authorization=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6.abc.def token",
                    "logger_name": "pay",
                },
                {"application": "checkout-api", "level": "INFO", "message": "order processed"},
                {
                    "application": "web",
                    "level": "WARNING",
                    "message": "slow query",
                    "attributes": {"password": "hunter2", "user": "michael"},
                },
            ],
        }
        r = await c.post(f"{BASE}/logs/ingest", json=logs, headers=key_headers)
        assert r.status_code == 202, r.text
        print("log ingest:", r.json())

        # 5. Host metrics ingestion
        metrics = {
            "metrics": [
                {
                    "host": "web-01",
                    "cpu_percent": 91.5,
                    "memory_percent": 62.0,
                    "disk_percent": 44.0,
                    "net_in_kb_per_s": 120.5,
                    "net_out_kb_per_s": 88.2,
                    "environment": "production",
                    "service_checks": {"nginx": True, "postgres": False},
                },
            ],
        }
        r = await c.post(f"{BASE}/infrastructure/ingest", json=metrics, headers=key_headers)
        assert r.status_code == 202, r.text
        print("metric ingest:", r.json())

        # 6. OTLP trace ingestion
        otlp = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "checkout-api"}},
                            {
                                "key": "deployment.environment",
                                "value": {"stringValue": "production"},
                            },
                        ],
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "tr123",
                                    "spanId": "s1",
                                    "name": "POST /checkout",
                                    "kind": 2,
                                    "startTimeUnixNano": str(int(1_700_000_000e9)),
                                    "endTimeUnixNano": str(int(1_700_000_001e9)),
                                    "status": {"code": 2, "message": "payment declined"},
                                    "attributes": [
                                        {"key": "http.status_code", "value": {"intValue": "502"}},
                                    ],
                                },
                                {
                                    "traceId": "tr123",
                                    "spanId": "s2",
                                    "parentSpanId": "s1",
                                    "name": "charge_card",
                                    "kind": 3,
                                    "startTimeUnixNano": str(int(1_700_000_000e9 + 1e6)),
                                    "endTimeUnixNano": str(int(1_700_000_000e9 + 5e8)),
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        r = await c.post(f"{BASE}/traces/ingest", json=otlp, headers=key_headers)
        assert r.status_code == 202, r.text
        print("trace ingest:", r.json())

        # 7. Query everything back (JWT side)
        r = await c.get(
            f"{BASE}/logs/?organization_id={org_id}&level=ERROR",
            headers=headers,
        )
        err_logs = r.json()
        assert err_logs["total"] == 1, err_logs
        msg = err_logs["logs"][0]["message"]
        print("log search (ERROR):", msg)
        assert "eyJ" not in msg, "JWT token was not redacted"
        assert "Bearer" in msg

        r = await c.get(
            f"{BASE}/logs/stats?organization_id={org_id}&period=24h",
            headers=headers,
        )
        stats = r.json()
        print(
            "log stats:",
            {k: stats[k] for k in ("total", "error_count", "errors_by_application")},
        )
        assert stats["total"] == 3 and stats["error_count"] == 1

        r = await c.get(
            f"{BASE}/infrastructure/hosts?organization_id={org_id}",
            headers=headers,
        )
        hosts = r.json()
        print("hosts:", [(h["host"], h["health"]) for h in hosts["hosts"]])

        r = await c.post(
            f"{BASE}/infrastructure/thresholds",
            json={
                "organization_id": org_id,
                "host": "web-01",
                "cpu_percent": 80,
                "process_names": ["nginx", "postgres"],
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text

        r = await c.get(f"{BASE}/traces/?organization_id={org_id}", headers=headers)
        traces = r.json()
        print(
            "traces:",
            [(t["trace_id"], t["span_count"], t["error_count"], t["root_operation"]) for t in traces["traces"]],
        )

        r = await c.get(
            f"{BASE}/traces/service-map?organization_id={org_id}&period=24h",
            headers=headers,
        )
        print("service map:", r.json())

        r = await c.get(
            f"{BASE}/analytics/service-health?organization_id={org_id}",
            headers=headers,
        )
        health = r.json()
        print("service-health counts:", health["counts"])

        # 8. Monitor + SLO
        r = await c.post(
            f"{BASE}/monitors/",
            json={
                "organization_id": org_id,
                "name": "API",
                "url": "https://api.example.com",
                "interval_seconds": 60,
                "environment": "production",
                "tags": ["payments", "critical"],
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        monitor = r.json()
        print("monitor tags/env:", monitor["tags"], monitor["environment"])

        r = await c.post(
            f"{BASE}/slos/",
            json={
                "organization_id": org_id,
                "monitor_id": monitor["public_id"],
                "name": "API 99.9",
                "target_percentage": 99.9,
                "window_days": 30,
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        slo_id = r.json()["id"]
        r = await c.get(f"{BASE}/slos/{slo_id}/status", headers=headers)
        slo_status = r.json()
        print(
            "slo status:",
            {
                k: slo_status[k]
                for k in ("attained_percentage", "target_met", "error_budget_remaining_percentage")
            },
        )

        # 9. Dashboard template
        r = await c.post(
            f"{BASE}/dashboards/",
            json={
                "organization_id": org_id,
                "name": "Ops Overview",
                "is_default": True,
                "widgets": [
                    {"type": "monitor_status", "title": "Services"},
                    {"type": "log_volume", "title": "Log volume"},
                    {"type": "host_health", "title": "Hosts"},
                ],
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        print("dashboard created:", r.json()["name"], "widgets:", len(r.json()["widgets"]))

        # 10. Monitor filters
        r = await c.get(f"{BASE}/monitors/?organization_id={org_id}&tag=critical", headers=headers)
        print("tag filter total:", r.json()["total"])
        r = await c.get(
            f"{BASE}/monitors/?organization_id={org_id}&environment=production",
            headers=headers,
        )
        print("environment filter total:", r.json()["total"])

        # 11. Wrong API key rejected
        r = await c.post(f"{BASE}/logs/ingest", json=logs, headers={"X-API-Key": "wd_live_bogus"})
        assert r.status_code == 401
        print("bogus key rejected: 401 OK")

    print("E2E COMPLETE: all checks passed")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
