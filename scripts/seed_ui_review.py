"""Seed rich demo data for the dashboard UI review.

Creates a dedicated review account (ui-reviewer@test.dev / StrongPass123) with
an organization, clients, monitors of every type, check histories, incidents,
alert channels, an API key, logs, host metrics + thresholds, traces, SLOs,
maintenance windows, a dashboard template, and a status page.

Run from the repo root:  PYTHONPATH=src python scripts/seed_ui_review.py
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from monitoring.core.security import hash_password
from monitoring.database import AsyncSessionLocal
from monitoring.models.alert import Alert
from monitoring.models.check_result import CheckResult
from monitoring.models.client import Client
from monitoring.models.dashboard_template import DashboardTemplate
from monitoring.models.host_metric import HostMetric, HostThreshold
from monitoring.models.incident import Incident, IncidentUpdate
from monitoring.models.log_entry import LogEntry
from monitoring.models.maintenance import MaintenanceWindow, MaintenanceWindowMonitor
from monitoring.models.monitor import Monitor
from monitoring.models.notification import NotificationChannel
from monitoring.models.organization import Organization, OrganizationMember
from monitoring.models.slo import SLO
from monitoring.models.status_page import StatusPage, StatusPageService
from monitoring.models.trace_span import TraceSpan
from monitoring.models.user import User
from monitoring.schemas.api_key import ApiKeyCreate
from monitoring.services.api_key_service import ApiKeyService

EMAIL = "ui-reviewer@test.dev"
PASSWORD = "StrongPass123"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # Fresh review user (keep other accounts untouched)
        user = User(
            full_name="UI Reviewer",
            email=EMAIL,
            password_hash=hash_password(PASSWORD),
            is_verified=True,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        org = Organization(name="Acme Studio", slug="acme-studio", owner_id=user.id)
        db.add(org)
        await db.flush()
        # The API auto-creates the owner membership; replicate it for direct seeds.
        db.add(
            OrganizationMember(
                organization_id=org.id,
                user_id=user.id,
                role="OWNER",
                status="ACTIVE",
            ),
        )
        await db.flush()

        acme = Client(organization_id=org.id, name="Acme Stores", contact_email="ops@acme.test")
        globex = Client(organization_id=org.id, name="Globex Ltd", contact_email="it@globex.test")
        db.add_all([acme, globex])
        await db.flush()

        now = datetime.now(UTC)

        def monitor(**kwargs):
            defaults = {
                "organization_id": org.id,
                "interval_seconds": 60,
                "enabled": True,
                "timeout_seconds": 5.0,
                "status": "UP",
                "last_checked_at": now - timedelta(minutes=1),
                "next_check_at": now + timedelta(minutes=1),
            }
            defaults.update(kwargs)
            return Monitor(**defaults)

        site = monitor(
            client_id=acme.id,
            name="Acme Storefront",
            url="https://acme.test",
            monitor_type="WEBSITE",
            environment="production",
            tags=["storefront", "revenue"],
        )
        api = monitor(
            client_id=acme.id,
            name="Checkout API",
            url="https://api.acme.test/health",
            monitor_type="API",
            expected_status_code=200,
            expected_json={"status": "ok"},
            environment="production",
            tags=["payments", "critical"],
        )
        down = monitor(
            client_id=globex.id,
            name="Globex Legacy Portal",
            url="https://legacy.globex.test",
            monitor_type="WEBSITE",
            status="DOWN",
            consecutive_failures=4,
            environment="staging",
            tags=["legacy"],
        )
        ssl_mon = monitor(
            client_id=acme.id,
            name="Acme SSL Certificate",
            url="https://acme.test",
            monitor_type="SSL",
            ssl_expiry_threshold_days=14,
            ssl_expires_at=now + timedelta(days=9),
            ssl_issuer="Let's Encrypt",
            status="DEGRADED",
            interval_seconds=86400,
        )
        dns_mon = monitor(
            client_id=globex.id,
            name="Globex DNS A record",
            url="globex.test",
            monitor_type="DNS",
            record_type="A",
            interval_seconds=300,
            status="UP",
            last_checked_at=now - timedelta(minutes=2),
        )
        tcp_mon = monitor(
            client_id=globex.id,
            name="Globex Postgres",
            url="tcp://db.globex.test",
            monitor_type="TCP",
            port=5432,
            interval_seconds=60,
            status="UP",
        )
        heartbeat = monitor(
            client_id=acme.id,
            name="Nightly DB Backup",
            monitor_type="HEARTBEAT",
            interval_seconds=3600,
            heartbeat_key=f"hb_{uuid.uuid4().hex[:12]}",
            status="UP",
            last_checked_at=now - timedelta(minutes=20),
            next_check_at=now + timedelta(minutes=40),
        )
        paused = monitor(
            client_id=globex.id,
            name="Globex CDN (paused)",
            url="https://cdn.globex.test",
            monitor_type="WEBSITE",
            enabled=False,
            status="PAUSED",
        )
        db.add_all([site, api, down, ssl_mon, dns_mon, tcp_mon, heartbeat, paused])
        await db.flush()

        # Check histories (last 6h) for charts
        for index in range(60):
            ts = now - timedelta(minutes=6 * index)
            for mon, base in [(site, 180.0), (api, 240.0), (tcp_mon, 15.0)]:
                db.add(
                    CheckResult(
                        organization_id=org.id,
                        monitor_id=mon.id,
                        success=index % 9 != 0,
                        status_code=200,
                        latency_ms=base + (index % 5) * 12,
                        checked_at=ts,
                    ),
                )
            # SSL monitor checks carry cert metadata
            db.add(
                CheckResult(
                    organization_id=org.id,
                    monitor_id=ssl_mon.id,
                    success=True,
                    latency_ms=45.0,
                    meta={
                        "ssl_expires_at": ssl_mon.ssl_expires_at.isoformat(),
                        "ssl_issuer": "Let's Encrypt",
                        "ssl_days_remaining": 9.0,
                        "degraded": True,
                    },
                    checked_at=ts,
                ),
            )
        # Failed checks for the down monitor
        for index in range(5):
            db.add(
                CheckResult(
                    organization_id=org.id,
                    monitor_id=down.id,
                    success=False,
                    error_message="Connection refused",
                    checked_at=now - timedelta(minutes=index + 1),
                ),
            )
        await db.flush()

        # Open incident for the down monitor + a resolved one
        open_incident = Incident(
            organization_id=org.id,
            monitor_id=down.id,
            title="Globex Legacy Portal is down",
            reason="Connection refused after 3 consecutive failures",
            severity="HIGH",
            status="OPEN",
            started_at=now - timedelta(minutes=48),
        )
        resolved_incident = Incident(
            organization_id=org.id,
            monitor_id=api.id,
            title="Checkout API latency spike",
            reason="Response time exceeded threshold",
            severity="MEDIUM",
            status="RESOLVED",
            started_at=now - timedelta(days=2),
            resolved_at=now - timedelta(days=2) + timedelta(minutes=37),
            duration_seconds=2220,
        )
        db.add_all([open_incident, resolved_incident])
        await db.flush()
        db.add_all(
            [
                IncidentUpdate(
                    incident_id=open_incident.id,
                    message="On-call engineer paged, investigating now.",
                    visibility="PUBLIC",
                ),
                IncidentUpdate(
                    incident_id=open_incident.id,
                    message="Upstream host is unreachable from the office network too.",
                    visibility="INTERNAL",
                ),
                IncidentUpdate(
                    incident_id=resolved_incident.id,
                    message="Deploy of checkout-service caused a latency regression; rolled back.",
                    visibility="PUBLIC",
                ),
            ],
        )
        db.add_all(
            [
                Alert(
                    monitor_id=down.id,
                    organization_id=org.id,
                    severity="error",
                    title="Monitor 'Globex Legacy Portal' has 3 consecutive failures",
                    message="Recent errors: Connection refused",
                    triggered_at=now - timedelta(minutes=45),
                ),
                Alert(
                    monitor_id=ssl_mon.id,
                    organization_id=org.id,
                    severity="warning",
                    title="SSL certificate for 'Acme SSL Certificate' expires soon",
                    message="The certificate expires in 9 days (threshold 14).",
                    triggered_at=now - timedelta(hours=3),
                ),
                Alert(
                    monitor_id=down.id,
                    organization_id=org.id,
                    severity="error",
                    title="Host 'web-01' resource threshold breached",
                    message="CPU 91.5% > 80%",
                    triggered_at=now - timedelta(minutes=10),
                ),
            ],
        )

        # Alert channels
        db.add_all(
            [
                NotificationChannel(
                    organization_id=org.id,
                    name="Ops Email",
                    channel_type="EMAIL",
                    config={"email": "ops@acme.test"},
                ),
                NotificationChannel(
                    organization_id=org.id,
                    name="Dev Telegram",
                    channel_type="TELEGRAM",
                    config={"chat_id": "123456789"},
                ),
            ],
        )

        # API key (raw printed once for the review session)
        api_key_service = ApiKeyService(db)
        _, raw_key = await api_key_service.create_key(
            org.id,
            ApiKeyCreate(organization_id=org.public_id, name="Review agent key"),
        )
        print(f"API_KEY={raw_key}")

        # Logs across 24h
        apps = ["checkout-api", "storefront", "worker"]
        messages = {
            "checkout-api": [
                ("ERROR", "Payment gateway timeout after 30s"),
                ("ERROR", "Order 58219 failed: card declined"),
                ("WARNING", "Cart service slow: 1.4s p95"),
                ("INFO", "Order 58220 completed"),
            ],
            "storefront": [
                ("INFO", "Page rendered in 82ms"),
                ("WARNING", "Image CDN cache miss rate 12%"),
                ("DEBUG", "Session gc reclaimed 34 keys"),
            ],
            "worker": [
                ("CRITICAL", "Backup job failed: pg_dump exited 2"),
                ("ERROR", "Queue depth above threshold: 1840"),
                ("INFO", "Nightly sync finished"),
            ],
        }
        for hours_ago in range(24):
            for app_index, app in enumerate(apps):
                level, message = messages[app][(hours_ago + app_index) % len(messages[app])]
                db.add(
                    LogEntry(
                        organization_id=org.id,
                        application=app,
                        environment="production",
                        level=level,
                        message=message,
                        logger_name=f"{app}.main",
                        host="web-01",
                        timestamp=now - timedelta(hours=hours_ago, minutes=app_index * 7),
                    ),
                )

        # Host metrics: web-01 critical, db-01 healthy
        for index in range(24):
            ts = now - timedelta(minutes=15 * index)
            db.add(
                HostMetric(
                    organization_id=org.id,
                    host="web-01",
                    environment="production",
                    cpu_percent=94 - index * 1.2 if index < 12 else 30 + (index % 10),
                    memory_percent=70.0 + (index % 4),
                    memory_used_mb=5800.0,
                    disk_percent=61.5,
                    disk_used_gb=210.4,
                    net_in_kb_per_s=120.5 - index,
                    net_out_kb_per_s=88.2 - index / 2,
                    processes=[
                        {"pid": 1, "name": "gunicorn", "cpu": 4.2, "memory": 1.8},
                        {"pid": 22, "name": "nginx", "cpu": 1.1, "memory": 0.6},
                    ],
                    service_checks={"gunicorn": True, "nginx": True},
                    measured_at=ts,
                ),
            )
            db.add(
                HostMetric(
                    organization_id=org.id,
                    host="db-01",
                    environment="production",
                    cpu_percent=22.0 + (index % 5),
                    memory_percent=48.0,
                    memory_used_mb=3200.0,
                    disk_percent=38.0,
                    disk_used_gb=140.2,
                    net_in_kb_per_s=40.0,
                    net_out_kb_per_s=64.0,
                    processes=[{"pid": 7, "name": "postgres", "cpu": 2.4, "memory": 3.1}],
                    service_checks={"postgres": True},
                    measured_at=ts,
                ),
            )
        db.add(
            HostThreshold(
                organization_id=org.id,
                host="web-01",
                cpu_percent=80,
                memory_percent=90,
                disk_percent=90,
                process_names=["gunicorn", "nginx"],
            ),
        )

        # Traces: checkout-api -> payment-provider, recent
        for trace_index in range(3):
            base = now - timedelta(minutes=12 * trace_index + 3)
            trace_id = f"trace-{trace_index:04d}abcdef"
            db.add_all(
                [
                    TraceSpan(
                        organization_id=org.id,
                        trace_id=trace_id,
                        span_id=f"root-{trace_index}",
                        service="checkout-api",
                        operation="POST /checkout",
                        kind="SERVER",
                        start_time=base,
                        end_time=base + timedelta(milliseconds=420),
                        duration_ms=420.0,
                        status="ERROR" if trace_index == 0 else "OK",
                        status_message="payment declined" if trace_index == 0 else None,
                    ),
                    TraceSpan(
                        organization_id=org.id,
                        trace_id=trace_id,
                        span_id=f"child-{trace_index}",
                        parent_span_id=f"root-{trace_index}",
                        service="payment-provider",
                        operation="charge_card",
                        kind="CLIENT",
                        start_time=base + timedelta(milliseconds=10),
                        end_time=base + timedelta(milliseconds=380),
                        duration_ms=370.0,
                        status="ERROR" if trace_index == 0 else "OK",
                    ),
                ],
            )

        # SLO for the API monitor
        db.add(
            SLO(
                organization_id=org.id,
                monitor_id=api.id,
                name="Checkout API 99.9%",
                description="Monthly availability for the checkout API",
                target_percentage=99.9,
                window_days=30,
            ),
        )
        db.add(
            SLO(
                organization_id=org.id,
                monitor_id=site.id,
                name="Storefront 99.5%",
                target_percentage=99.5,
                window_days=30,
            ),
        )

        # Maintenance windows: one active, one upcoming
        active_window = MaintenanceWindow(
            organization_id=org.id,
            title="Legacy portal migration",
            description="Moving Globex legacy portal to new hosting",
            starts_at=now - timedelta(minutes=30),
            ends_at=now + timedelta(hours=2),
            notify_subscribers=True,
        )
        upcoming_window = MaintenanceWindow(
            organization_id=org.id,
            title="Storefront deploy freeze",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=3),
        )
        db.add_all([active_window, upcoming_window])
        await db.flush()
        db.add(
            MaintenanceWindowMonitor(
                maintenance_window_id=active_window.id,
                monitor_id=down.id,
            ),
        )

        # Dashboard template
        db.add(
            DashboardTemplate(
                organization_id=org.id,
                name="Ops Overview",
                description="Default on-call view",
                is_default=True,
                widgets=[
                    {"type": "monitor_status", "title": "Services", "config": {}},
                    {"type": "log_volume", "title": "Log volume (24h)", "config": {}},
                    {"type": "host_health", "title": "Hosts", "config": {}},
                    {"type": "slo_status", "title": "SLOs", "config": {}},
                ],
            ),
        )

        # Status page
        page = StatusPage(
            organization_id=org.id,
            name="Acme Stores Status",
            slug="acme-stores",
            brand_color="#2563eb",
            is_active=True,
        )
        db.add(page)
        await db.flush()
        db.add_all(
            [
                StatusPageService(
                    status_page_id=page.id,
                    monitor_id=site.id,
                    display_name="Storefront",
                    sort_order=0,
                    is_visible=True,
                ),
                StatusPageService(
                    status_page_id=page.id,
                    monitor_id=api.id,
                    display_name="Checkout API",
                    sort_order=1,
                    is_visible=True,
                ),
            ],
        )

        await db.commit()
        print("SEEDED org=acme-studio email=ui-reviewer@test.dev password=StrongPass123")


if __name__ == "__main__":
    asyncio.run(main())
