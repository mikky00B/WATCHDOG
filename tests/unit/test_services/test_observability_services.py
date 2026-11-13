"""Tests for the observability services: maintenance, API keys, logs, infra, traces, SLOs, dashboards, analytics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from monitoring.models.check_result import CheckResult
from monitoring.models.client import Client
from monitoring.models.host_metric import HostMetric, HostThreshold
from monitoring.models.log_entry import LogEntry
from monitoring.models.monitor import Monitor
from monitoring.models.organization import Organization
from monitoring.models.trace_span import TraceSpan
from monitoring.models.user import User
from monitoring.schemas.api_key import ApiKeyCreate
from monitoring.schemas.dashboard import (
    DashboardTemplateCreate,
    DashboardTemplateUpdate,
    WidgetConfig,
)
from monitoring.schemas.infrastructure import HostMetricIngest, HostThresholdCreate
from monitoring.schemas.log import LogEntryIngest
from monitoring.schemas.maintenance import MaintenanceWindowCreate
from monitoring.schemas.slo import SLOCreate
from monitoring.services.analytics_service import AnalyticsService
from monitoring.services.api_key_service import ApiKeyService, hash_api_key
from monitoring.services.dashboard_service import DashboardService
from monitoring.services.infrastructure_service import InfrastructureService
from monitoring.services.log_service import LogService
from monitoring.services.maintenance_service import MaintenanceService
from monitoring.services.slo_service import SLOService
from monitoring.services.trace_service import TraceService


async def make_org(test_db) -> Organization:
    """Create a verified user and organization directly in the test database."""
    user = User(
        full_name="Org Owner",
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        is_active=True,
        is_verified=True,
    )
    test_db.add(user)
    await test_db.flush()
    organization = Organization(
        name="Observability Org",
        slug=f"obs-{uuid.uuid4().hex[:8]}",
        owner_id=user.id,
    )
    test_db.add(organization)
    await test_db.flush()
    await test_db.refresh(organization)
    return organization


async def make_monitor(test_db, organization: Organization, **kwargs) -> Monitor:
    defaults = {
        "organization_id": organization.id,
        "name": f"Monitor {uuid.uuid4().hex[:6]}",
        "url": "https://api.example.com",
        "monitor_type": "WEBSITE",
        "interval_seconds": 60,
        "enabled": True,
    }
    defaults.update(kwargs)
    monitor = Monitor(**defaults)
    test_db.add(monitor)
    await test_db.flush()
    await test_db.refresh(monitor)
    return monitor


# ── Maintenance windows ────────────────────────────────────────────────────


class TestMaintenanceService:
    async def test_create_and_list(self, test_db) -> None:
        org = await make_org(test_db)
        monitor = await make_monitor(test_db, org)
        service = MaintenanceService(test_db)
        await service.create_window(
            MaintenanceWindowCreate(
                organization_id=org.public_id,
                title="DB upgrade",
                starts_at=datetime.now(UTC) + timedelta(hours=1),
                ends_at=datetime.now(UTC) + timedelta(hours=3),
                monitor_ids=[monitor.public_id],
            ),
        )
        windows, total = await service.list_windows(org.id)
        assert total == 1 and windows[0].title == "DB upgrade"
        assert windows[0].monitors[0].monitor_id == monitor.id

    async def test_unknown_monitor_rejected(self, test_db) -> None:
        org = await make_org(test_db)
        service = MaintenanceService(test_db)
        with pytest.raises(ValueError, match="not found"):
            await service.create_window(
                MaintenanceWindowCreate(
                    organization_id=org.public_id,
                    title="Bad",
                    starts_at=datetime.now(UTC),
                    ends_at=datetime.now(UTC) + timedelta(hours=1),
                    monitor_ids=[uuid.uuid4()],
                ),
            )

    async def test_suppressed_monitor_ids_scoped(self, test_db) -> None:
        org = await make_org(test_db)
        monitor = await make_monitor(test_db, org)
        other_org = await make_org(test_db)
        other_monitor = await make_monitor(test_db, other_org)
        service = MaintenanceService(test_db)
        now = datetime.now(UTC)
        await service.create_window(
            MaintenanceWindowCreate(
                organization_id=org.public_id,
                title="Active window",
                starts_at=now - timedelta(minutes=10),
                ends_at=now + timedelta(hours=1),
                monitor_ids=[monitor.public_id],
            ),
        )
        suppressed = await service.get_suppressed_monitor_ids()
        assert monitor.id in suppressed
        assert other_monitor.id not in suppressed

    async def test_orgwide_window_suppresses_all(self, test_db) -> None:
        org = await make_org(test_db)
        await make_monitor(test_db, org)
        await make_monitor(test_db, org)
        service = MaintenanceService(test_db)
        now = datetime.now(UTC)
        await service.create_window(
            MaintenanceWindowCreate(
                organization_id=org.public_id,
                title="Org-wide",
                starts_at=now - timedelta(minutes=5),
                ends_at=now + timedelta(hours=1),
            ),
        )
        suppressed = await service.get_suppressed_monitor_ids()
        assert len(suppressed) == 2

    async def test_public_payload_statuses(self, test_db) -> None:
        org = await make_org(test_db)
        service = MaintenanceService(test_db)
        now = datetime.now(UTC)
        await service.create_window(
            MaintenanceWindowCreate(
                organization_id=org.public_id,
                title="In progress",
                starts_at=now - timedelta(minutes=5),
                ends_at=now + timedelta(hours=1),
            ),
        )
        await service.create_window(
            MaintenanceWindowCreate(
                organization_id=org.public_id,
                title="Upcoming",
                starts_at=now + timedelta(hours=1),
                ends_at=now + timedelta(hours=2),
            ),
        )
        payload = await service.public_maintenance_payload(org.id)
        assert {item["status"] for item in payload} == {"IN_PROGRESS", "SCHEDULED"}

    async def test_update_and_delete(self, test_db) -> None:
        org = await make_org(test_db)
        service = MaintenanceService(test_db)
        window = await service.create_window(
            MaintenanceWindowCreate(
                organization_id=org.public_id,
                title="Original",
                starts_at=datetime.now(UTC),
                ends_at=datetime.now(UTC) + timedelta(hours=1),
            ),
        )
        from monitoring.schemas.maintenance import MaintenanceWindowUpdate

        updated = await service.update_window(window.public_id, MaintenanceWindowUpdate(title="Renamed"))
        assert updated is not None and updated.title == "Renamed"
        assert await service.delete_window(window.public_id) is True
        windows, total = await service.list_windows(org.id)
        assert total == 0 and windows == []


# ── API keys ───────────────────────────────────────────────────────────────


class TestApiKeyService:
    async def test_create_returns_raw_key_once(self, test_db) -> None:
        org = await make_org(test_db)
        service = ApiKeyService(test_db)
        api_key, raw_key = await service.create_key(org.id, ApiKeyCreate(organization_id=org.public_id, name="agent"))
        assert raw_key.startswith("wd_live_")
        assert raw_key not in api_key.key_hash
        assert api_key.key_prefix in raw_key

    async def test_authenticate_roundtrip(self, test_db) -> None:
        org = await make_org(test_db)
        service = ApiKeyService(test_db)
        _, raw_key = await service.create_key(org.id, ApiKeyCreate(organization_id=org.public_id, name="k"))
        found = await service.authenticate(raw_key)
        assert found is not None and found.organization_id == org.id
        assert await service.authenticate("wd_live_wrong") is None
        assert await service.authenticate("") is None

    async def test_revoked_key_rejected(self, test_db) -> None:
        org = await make_org(test_db)
        service = ApiKeyService(test_db)
        api_key, raw_key = await service.create_key(org.id, ApiKeyCreate(organization_id=org.public_id, name="k"))
        await service.revoke_key(api_key.public_id)
        assert await service.authenticate(raw_key) is None

    async def test_expired_key_rejected(self, test_db) -> None:
        org = await make_org(test_db)
        service = ApiKeyService(test_db)
        api_key, raw_key = await service.create_key(
            org.id,
            ApiKeyCreate(
                organization_id=org.public_id,
                name="k",
                expires_at=datetime.now(UTC) - timedelta(days=1),
            ),
        )
        assert api_key.expires_at is not None
        assert await service.authenticate(raw_key) is None

    async def test_hash_is_stable_sha256(self) -> None:
        assert hash_api_key("abc") == hash_api_key("abc")
        assert hash_api_key("abc") != hash_api_key("abd")
        assert len(hash_api_key("abc")) == 64

    async def test_unknown_scope_rejected(self, test_db) -> None:
        org = await make_org(test_db)
        service = ApiKeyService(test_db)
        with pytest.raises(ValueError, match="Unknown scopes"):
            await service.create_key(
                org.id,
                ApiKeyCreate(organization_id=org.public_id, name="k", scopes=["bogus:scope"]),
            )


# ── Logs ───────────────────────────────────────────────────────────────────


class TestLogService:
    async def _ingest_sample(self, test_db, organization_id: int) -> tuple[int, int]:
        return await LogService(test_db).ingest(
            organization_id,
            [
                LogEntryIngest(application="checkout-api", level="ERROR", message="payment declined"),
                LogEntryIngest(application="checkout-api", level="warn", message="slow query"),
                LogEntryIngest(application="web", level="INFO", message="page served"),
            ],
        )

    async def test_ingest_normalizes_levels(self, test_db) -> None:
        org = await make_org(test_db)
        accepted, rejected = await self._ingest_sample(test_db, org.id)
        assert accepted == 3 and rejected == 0
        logs, total = await LogService(test_db).search_logs(org.id, level="warning,error")
        assert total == 2
        assert {entry.level for entry in logs} == {"WARNING", "ERROR"}

    async def test_invalid_level_rejected(self, test_db) -> None:
        org = await make_org(test_db)
        accepted, rejected = await LogService(test_db).ingest(
            org.id,
            [LogEntryIngest(application="app", level="BOGUS", message="x")],
        )
        assert accepted == 0 and rejected == 1

    async def test_redaction_applied_on_ingest(self, test_db) -> None:
        org = await make_org(test_db)
        await LogService(test_db).ingest(
            org.id,
            [
                LogEntryIngest(
                    application="app",
                    level="ERROR",
                    message="failed with token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.sig12345678",
                ),
            ],
        )
        logs, _ = await LogService(test_db).search_logs(org.id)
        assert "eyJhbGciOiJIUzI1NiIs" not in logs[0].message
        assert "[REDACTED]" in logs[0].message

    async def test_search_filters(self, test_db) -> None:
        org = await make_org(test_db)
        await self._ingest_sample(test_db, org.id)
        service = LogService(test_db)
        logs, total = await service.search_logs(org.id, application="checkout-api", search="payment")
        assert total == 1 and logs[0].message == "payment declined"
        _, total_all = await service.search_logs(org.id)
        assert total_all == 3

    async def test_org_isolation(self, test_db) -> None:
        org_a = await make_org(test_db)
        org_b = await make_org(test_db)
        await self._ingest_sample(test_db, org_a.id)
        _, total_b = await LogService(test_db).search_logs(org_b.id)
        assert total_b == 0

    async def test_stats_counts_and_buckets(self, test_db) -> None:
        org = await make_org(test_db)
        await self._ingest_sample(test_db, org.id)
        stats = await LogService(test_db).stats(org.id, hours=24)
        assert stats["total"] == 3
        assert stats["by_level"]["ERROR"] == 1
        assert stats["error_count"] == 1
        assert stats["errors_by_application"] == {"checkout-api": 1}
        assert len(stats["volume"]) >= 1
        bucket = stats["volume"][0]
        assert bucket.total == 3 and bucket.error == 1

    async def test_retention_deletes_old_only(self, test_db) -> None:
        org = await make_org(test_db)
        service = LogService(test_db)
        now = datetime.now(UTC)
        test_db.add(
            LogEntry(
                organization_id=org.id,
                application="old-app",
                level="INFO",
                message="ancient",
                timestamp=now - timedelta(days=90),
            ),
        )
        test_db.add(
            LogEntry(
                organization_id=org.id,
                application="app",
                level="INFO",
                message="recent",
                timestamp=now,
            ),
        )
        await test_db.flush()
        deleted = await service.delete_older_than(days=30)
        assert deleted == 1
        _, total = await service.search_logs(org.id)
        assert total == 1


# ── Infrastructure ─────────────────────────────────────────────────────────


class TestInfrastructureService:
    async def _ingest(self, test_db, organization_id: int, **metric_kwargs) -> None:
        defaults = {"host": "web-01", "cpu_percent": 50.0, "memory_percent": 60.0, "disk_percent": 40.0}
        defaults.update(metric_kwargs)
        accepted = await InfrastructureService(test_db).ingest_metrics(
            organization_id,
            [HostMetricIngest(**defaults)],
        )
        assert accepted == 1

    async def test_ingest_and_list_hosts(self, test_db) -> None:
        org = await make_org(test_db)
        await self._ingest(test_db, org.id, environment="production")
        summary = await InfrastructureService(test_db).list_hosts(org.id)
        assert summary[0].host == "web-01"
        assert summary[0].health == "OK"
        assert summary[0].latest.cpu_percent == 50.0

    async def test_health_states(self, test_db) -> None:
        org = await make_org(test_db)
        service = InfrastructureService(test_db)
        threshold = HostThreshold(
            organization_id=org.id,
            host="web-01",
            cpu_percent=80,
            memory_percent=90,
            disk_percent=90,
        )
        test_db.add(threshold)
        await test_db.flush()
        metric = HostMetric(
            organization_id=org.id,
            host="web-01",
            cpu_percent=85.0,
            measured_at=datetime.now(UTC),
        )
        assert service._health(metric, threshold) == "CRITICAL"
        metric.cpu_percent = 75.0  # >= 80 * 0.9 warning margin
        assert service._health(metric, threshold) == "WARNING"
        metric.cpu_percent = 50.0
        assert service._health(metric, threshold) == "OK"

    async def test_missing_service_breach(self, test_db) -> None:
        org = await make_org(test_db)
        service = InfrastructureService(test_db)
        threshold = HostThreshold(organization_id=org.id, host="web-01", process_names=["nginx"])
        await test_db.flush()
        metric = HostMetric(
            organization_id=org.id,
            host="web-01",
            cpu_percent=10.0,
            service_checks={"nginx": False},
            measured_at=datetime.now(UTC),
        )
        breaches = service._breaches(metric, threshold)
        assert any("nginx" in detail for _, detail in breaches)

    async def test_threshold_evaluation_creates_and_dedups_alert(self, test_db) -> None:
        org = await make_org(test_db)
        service = InfrastructureService(test_db)
        await service.upsert_threshold(
            org.id,
            HostThresholdCreate(organization_id=org.public_id, host="web-01", cpu_percent=80),
        )
        await self._ingest(test_db, org.id, cpu_percent=95.0)
        alerts = await service.evaluate_thresholds()
        assert len(alerts) == 1
        assert alerts[0].organization_id == org.id
        # Second run within the dedup window creates nothing new
        alerts_again = await service.evaluate_thresholds()
        assert alerts_again == []

    async def test_no_alert_below_threshold(self, test_db) -> None:
        org = await make_org(test_db)
        service = InfrastructureService(test_db)
        await service.upsert_threshold(
            org.id,
            HostThresholdCreate(organization_id=org.public_id, host="web-01", cpu_percent=99),
        )
        await self._ingest(test_db, org.id, cpu_percent=10.0)
        assert await service.evaluate_thresholds() == []

    async def test_metric_retention(self, test_db) -> None:
        org = await make_org(test_db)
        now = datetime.now(UTC)
        test_db.add(HostMetric(organization_id=org.id, host="old", measured_at=now - timedelta(days=30)))
        test_db.add(HostMetric(organization_id=org.id, host="new", measured_at=now))
        await test_db.flush()
        deleted = await InfrastructureService(test_db).delete_older_than(days=14)
        assert deleted == 1


# ── Traces ─────────────────────────────────────────────────────────────────


class TestTraceService:
    def _otlp_payload(self) -> dict:
        base_ns = int(datetime.now(UTC).timestamp() * 1e9)
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "checkout-api"}},
                            {"key": "deployment.environment", "value": {"stringValue": "production"}},
                        ],
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "trace-1",
                                    "spanId": "s1",
                                    "name": "POST /checkout",
                                    "kind": 2,
                                    "startTimeUnixNano": str(base_ns),
                                    "endTimeUnixNano": str(base_ns + 500_000_000),
                                    "status": {"code": 2, "message": "boom"},
                                },
                                {
                                    "traceId": "trace-1",
                                    "spanId": "s2",
                                    "parentSpanId": "s1",
                                    "name": "charge_card",
                                    "kind": 3,
                                    "startTimeUnixNano": str(base_ns + 10_000_000),
                                    "endTimeUnixNano": str(base_ns + 200_000_000),
                                },
                            ],
                        },
                    ],
                },
            ],
        }

    async def test_otlp_ingest_parses_fields(self, test_db) -> None:
        org = await make_org(test_db)
        service = TraceService(test_db)
        accepted = await service.ingest_otlp_json(org.id, self._otlp_payload())
        assert accepted == 2
        spans = await service.get_trace(org.id, "trace-1")
        root = next(span for span in spans if span.span_id == "s1")
        assert root.service == "checkout-api"
        assert root.operation == "POST /checkout"
        assert root.kind == "SERVER"
        assert root.status == "ERROR"
        assert root.duration_ms == pytest.approx(500.0)
        assert root.environment == "production"
        child = next(span for span in spans if span.span_id == "s2")
        assert child.parent_span_id == "s1"

    async def test_service_map_edges(self, test_db) -> None:
        org = await make_org(test_db)
        service = TraceService(test_db)
        await service.ingest_otlp_json(org.id, self._otlp_payload())
        # Add a third service span parented by the checkout-api root
        now = datetime.now(UTC)
        test_db.add(
            TraceSpan(
                organization_id=org.id,
                trace_id="trace-1",
                span_id="s3",
                parent_span_id="s1",
                service="payment-provider",
                operation="charge",
                start_time=now - timedelta(seconds=1),
                end_time=now,
                duration_ms=120.0,
            ),
        )
        await test_db.flush()
        service_map = await service.service_map(org.id, hours=24)
        edge = next(
            e
            for e in service_map["edges"]
            if e["source"] == "checkout-api" and e["target"] == "payment-provider"
        )
        assert edge["call_count"] == 1
        assert set(service_map["services"]) == {"checkout-api", "payment-provider"}

    async def test_list_traces_summarizes(self, test_db) -> None:
        org = await make_org(test_db)
        service = TraceService(test_db)
        await service.ingest_otlp_json(org.id, self._otlp_payload())
        traces = await service.list_traces(org.id, hours=24)
        assert len(traces) == 1
        summary = traces[0]
        assert summary["trace_id"] == "trace-1"
        assert summary["span_count"] == 2
        assert summary["error_count"] == 1
        assert summary["root_operation"] == "POST /checkout"

    async def test_org_isolation(self, test_db) -> None:
        org_a = await make_org(test_db)
        org_b = await make_org(test_db)
        service = TraceService(test_db)
        await service.ingest_otlp_json(org_a.id, self._otlp_payload())
        assert await service.get_trace(org_b.id, "trace-1") == []

    async def test_retention(self, test_db) -> None:
        org = await make_org(test_db)
        now = datetime.now(UTC)
        test_db.add(TraceSpan(organization_id=org.id, trace_id="t", span_id="a", service="s", operation="o", start_time=now - timedelta(days=30)))
        test_db.add(TraceSpan(organization_id=org.id, trace_id="t", span_id="b", service="s", operation="o", start_time=now))
        await test_db.flush()
        assert await TraceService(test_db).delete_older_than(days=7) == 1


# ── SLOs ───────────────────────────────────────────────────────────────────


class TestSloService:
    async def test_create_and_compute_status(self, test_db) -> None:
        org = await make_org(test_db)
        monitor = await make_monitor(test_db, org)
        service = SLOService(test_db)
        slo = await service.create_slo(
            SLOCreate(
                organization_id=org.public_id,
                monitor_id=monitor.public_id,
                name="API 99.9",
                target_percentage=99.9,
                window_days=30,
            ),
        )
        now = datetime.now(UTC)
        for index in range(99):
            test_db.add(
                CheckResult(monitor_id=monitor.id, success=True, latency_ms=100.0, checked_at=now - timedelta(minutes=index + 1)),
            )
        test_db.add(CheckResult(monitor_id=monitor.id, success=False, checked_at=now - timedelta(minutes=1)))
        await test_db.flush()

        status = await service.compute_status(slo)
        assert status["total_checks"] == 100
        assert status["successful_checks"] == 99
        assert status["attained_percentage"] == pytest.approx(99.0)
        assert status["target_met"] is False
        # 1% failure against a 0.1% budget consumes it entirely
        assert status["error_budget_remaining_percentage"] == 0.0

    async def test_perfect_attainment(self, test_db) -> None:
        org = await make_org(test_db)
        monitor = await make_monitor(test_db, org)
        service = SLOService(test_db)
        slo = await service.create_slo(
            SLOCreate(organization_id=org.public_id, monitor_id=monitor.public_id, name="Full", target_percentage=99.0, window_days=30),
        )
        test_db.add(CheckResult(monitor_id=monitor.id, success=True, checked_at=datetime.now(UTC)))
        await test_db.flush()
        status = await service.compute_status(slo)
        assert status["target_met"] is True
        assert status["error_budget_remaining_percentage"] == 100.0

    async def test_monitor_from_other_org_rejected(self, test_db) -> None:
        org_a = await make_org(test_db)
        org_b = await make_org(test_db)
        other_monitor = await make_monitor(test_db, org_b)
        service = SLOService(test_db)
        with pytest.raises(ValueError, match="Monitor not found"):
            await service.create_slo(
                SLOCreate(organization_id=org_a.public_id, monitor_id=other_monitor.public_id, name="Bad", target_percentage=99),
            )


# ── Dashboards ─────────────────────────────────────────────────────────────


class TestDashboardService:
    async def test_create_with_widgets(self, test_db) -> None:
        org = await make_org(test_db)
        service = DashboardService(test_db)
        await service.create_dashboard(
            DashboardTemplateCreate(
                organization_id=org.public_id,
                name="Ops Overview",
                widgets=[WidgetConfig(type="monitor_status", title="Services"), WidgetConfig(type="log_volume", title="Logs")],
            ),
        )
        found, total = await service.list_dashboards(org.id)
        assert total == 1
        assert [widget["type"] for widget in found[0].widgets] == ["monitor_status", "log_volume"]

    async def test_default_flag_clears_previous(self, test_db) -> None:
        org = await make_org(test_db)
        service = DashboardService(test_db)
        first = await service.create_dashboard(
            DashboardTemplateCreate(organization_id=org.public_id, name="First", is_default=True),
        )
        second = await service.create_dashboard(
            DashboardTemplateCreate(organization_id=org.public_id, name="Second", is_default=True),
        )
        await test_db.refresh(first)
        assert second.is_default is True
        assert first.is_default is False

    async def test_update_and_delete(self, test_db) -> None:
        org = await make_org(test_db)
        service = DashboardService(test_db)
        dashboard = await service.create_dashboard(
            DashboardTemplateCreate(organization_id=org.public_id, name="Original"),
        )
        updated = await service.update_dashboard(
            dashboard.public_id,
            DashboardTemplateUpdate(name="Renamed", widgets=[WidgetConfig(type="uptime", title="Uptime")]),
        )
        assert updated is not None
        assert updated.name == "Renamed"
        assert updated.widgets[0]["type"] == "uptime"
        assert await service.delete_dashboard(dashboard.public_id) is True


# ── Analytics ──────────────────────────────────────────────────────────────


class TestAnalyticsService:
    async def _seed_checks(self, test_db, organization_id: int, monitor_id: int) -> None:
        now = datetime.now(UTC)
        for index in range(10):
            test_db.add(
                CheckResult(
                    organization_id=organization_id,
                    monitor_id=monitor_id,
                    success=index % 4 != 0,  # 75% success
                    latency_ms=100.0 + index * 10,
                    checked_at=now - timedelta(hours=1, minutes=index),
                ),
            )
        await test_db.flush()

    async def test_response_time_series(self, test_db) -> None:
        org = await make_org(test_db)
        monitor = await make_monitor(test_db, org)
        await self._seed_checks(test_db, org.id, monitor.id)
        series = await AnalyticsService(test_db).response_time_series(org.id, hours=24)
        assert len(series) >= 1
        bucket = series[0]
        assert bucket["count"] == 10
        assert bucket["avg_ms"] == pytest.approx(145.0, abs=1.0)
        assert bucket["p95_ms"] is not None

    async def test_uptime_series(self, test_db) -> None:
        org = await make_org(test_db)
        monitor = await make_monitor(test_db, org)
        await self._seed_checks(test_db, org.id, monitor.id)
        series = await AnalyticsService(test_db).uptime_series(org.id, hours=24)
        assert series[0]["uptime_percentage"] == pytest.approx(70.0)

    async def test_service_health(self, test_db) -> None:
        org = await make_org(test_db)
        monitor = await make_monitor(test_db, org, environment="production", tags=["critical"])
        client = Client(organization_id=org.id, name="Acme")
        test_db.add(client)
        await test_db.flush()
        monitor.client_id = client.id
        await self._seed_checks(test_db, org.id, monitor.id)
        health = await AnalyticsService(test_db).service_health(org.id)
        assert health["counts"]["UP"] == 0 or health["counts"]["OTHER"] >= 0
        entry = health["services"][0]
        assert entry["uptime_24h"] == pytest.approx(70.0)
        assert entry["client_name"] == "Acme"
        assert entry["tags"] == ["critical"]
        assert entry["environment"] == "production"
        assert entry["in_maintenance"] is False

    async def test_incident_timeline_correlates(self, test_db) -> None:
        from monitoring.models.incident import Incident, IncidentUpdate

        org = await make_org(test_db)
        monitor = await make_monitor(test_db, org)
        now = datetime.now(UTC)
        incident = Incident(
            organization_id=org.id,
            monitor_id=monitor.id,
            title="Monitor down",
            reason="Connection refused",
            severity="HIGH",
            started_at=now - timedelta(minutes=30),
        )
        test_db.add(incident)
        await test_db.flush()
        test_db.add(IncidentUpdate(incident_id=incident.id, message="Investigating", visibility="INTERNAL"))
        test_db.add(
            CheckResult(
                organization_id=org.id,
                monitor_id=monitor.id,
                success=False,
                error_message="Connection refused",
                checked_at=now - timedelta(minutes=29),
            ),
        )
        test_db.add(
            LogEntry(
                organization_id=org.id,
                application="checkout-api",
                level="ERROR",
                message="connection refused downstream",
                timestamp=now - timedelta(minutes=28),
            ),
        )
        await test_db.flush()
        timeline = await AnalyticsService(test_db).incident_timeline(incident)
        kinds = [event["kind"] for event in timeline["events"]]
        assert "incident" in kinds
        assert "update" in kinds
        assert "check" in kinds
        assert "log" in kinds
        timestamps = [event["timestamp"] for event in timeline["events"]]
        assert timestamps == sorted(timestamps, key=lambda ts: (ts is None, ts))
