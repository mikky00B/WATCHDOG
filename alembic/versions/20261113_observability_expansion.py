"""Observability expansion: maintenance windows, API keys, logs, infra metrics, traces, SLOs, dashboards.

Revision ID: 20261113_observability
Revises: 20260522_auth_hardening
Create Date: 2026-11-13

Adds:
- Phase 1: monitor columns (environment, tags, TCP/DNS config, SSL tracking),
  expected response headers, check_results metadata, maintenance windows.
- Phase 2: API keys and ingested application log entries.
- Phase 3: host metrics and host thresholds.
- Phase 4: dashboard templates.
- Phase 5: trace spans and SLOs.
Also relaxes alerts.monitor_id to nullable for infrastructure alerts.
"""

from __future__ import annotations

from alembic import op

revision = "20261113_observability"
down_revision = "20260522_auth_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Monitor extensions ────────────────────────────────────────────────
    op.execute(
        """
        ALTER TABLE monitors
            ADD COLUMN IF NOT EXISTS environment VARCHAR(50),
            ADD COLUMN IF NOT EXISTS tags JSONB,
            ADD COLUMN IF NOT EXISTS expected_headers JSONB,
            ADD COLUMN IF NOT EXISTS port INTEGER,
            ADD COLUMN IF NOT EXISTS record_type VARCHAR(20),
            ADD COLUMN IF NOT EXISTS expected_values JSONB,
            ADD COLUMN IF NOT EXISTS ssl_expiry_threshold_days INTEGER,
            ADD COLUMN IF NOT EXISTS ssl_expires_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN IF NOT EXISTS ssl_issuer VARCHAR(255)
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_monitors_environment ON monitors (environment)")

    op.execute("ALTER TABLE check_results ADD COLUMN IF NOT EXISTS meta JSONB")

    # Infrastructure alerts have no monitor.
    op.execute("ALTER TABLE alerts ALTER COLUMN monitor_id DROP NOT NULL")

    # ── Maintenance windows ───────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_windows (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            public_id UUID NOT NULL UNIQUE,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
            ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
            notify_subscribers BOOLEAN NOT NULL DEFAULT FALSE,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_maintenance_windows_organization_id "
        "ON maintenance_windows (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_maintenance_windows_starts_at "
        "ON maintenance_windows (starts_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_maintenance_windows_ends_at "
        "ON maintenance_windows (ends_at)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_window_monitors (
            id SERIAL PRIMARY KEY,
            maintenance_window_id INTEGER NOT NULL
                REFERENCES maintenance_windows(id) ON DELETE CASCADE,
            monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
            CONSTRAINT uq_maintenance_window_monitor
                UNIQUE (maintenance_window_id, monitor_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_maintenance_window_monitors_window_id "
        "ON maintenance_window_monitors (maintenance_window_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_maintenance_window_monitors_monitor_id "
        "ON maintenance_window_monitors (monitor_id)"
    )

    # ── API keys ──────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            public_id UUID NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            key_prefix VARCHAR(32) NOT NULL,
            key_hash VARCHAR(128) NOT NULL UNIQUE,
            permissions JSONB,
            last_used_at TIMESTAMP WITH TIME ZONE,
            expires_at TIMESTAMP WITH TIME ZONE,
            revoked_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_api_keys_organization_id ON api_keys (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash)"
    )

    # ── Log entries ───────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS log_entries (
            id BIGSERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            application VARCHAR(255) NOT NULL,
            environment VARCHAR(50),
            level VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            logger_name VARCHAR(255),
            host VARCHAR(255),
            trace_id VARCHAR(64),
            span_id VARCHAR(64),
            attributes JSONB,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_log_entries_organization_id ON log_entries (organization_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_log_entries_application ON log_entries (application)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_log_entries_level ON log_entries (level)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_log_entries_timestamp ON log_entries (timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_log_entries_trace_id ON log_entries (trace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_log_entries_client_id ON log_entries (client_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_log_entries_environment ON log_entries (environment)"
    )

    # ── Host metrics and thresholds ───────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS host_metrics (
            id BIGSERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            host VARCHAR(255) NOT NULL,
            environment VARCHAR(50),
            cpu_percent DOUBLE PRECISION,
            memory_percent DOUBLE PRECISION,
            memory_used_mb DOUBLE PRECISION,
            disk_percent DOUBLE PRECISION,
            disk_used_gb DOUBLE PRECISION,
            net_in_kb_per_s DOUBLE PRECISION,
            net_out_kb_per_s DOUBLE PRECISION,
            processes JSONB,
            service_checks JSONB,
            measured_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_host_metrics_organization_id "
        "ON host_metrics (organization_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_host_metrics_host ON host_metrics (host)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_host_metrics_measured_at ON host_metrics (measured_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_host_metrics_client_id ON host_metrics (client_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS host_thresholds (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            host VARCHAR(255) NOT NULL,
            cpu_percent DOUBLE PRECISION,
            memory_percent DOUBLE PRECISION,
            disk_percent DOUBLE PRECISION,
            process_names JSONB,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_host_threshold_org_host UNIQUE (organization_id, host)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_host_thresholds_organization_id "
        "ON host_thresholds (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_host_thresholds_host ON host_thresholds (host)"
    )

    # ── Trace spans ───────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_spans (
            id BIGSERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            application VARCHAR(255),
            environment VARCHAR(50),
            trace_id VARCHAR(64) NOT NULL,
            span_id VARCHAR(64) NOT NULL,
            parent_span_id VARCHAR(64),
            service VARCHAR(255) NOT NULL,
            operation VARCHAR(255) NOT NULL,
            kind VARCHAR(20),
            start_time TIMESTAMP WITH TIME ZONE NOT NULL,
            end_time TIMESTAMP WITH TIME ZONE,
            duration_ms DOUBLE PRECISION,
            status VARCHAR(20) NOT NULL DEFAULT 'UNSET',
            status_message TEXT,
            attributes JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trace_spans_organization_id "
        "ON trace_spans (organization_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_trace_spans_trace_id ON trace_spans (trace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_trace_spans_service ON trace_spans (service)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_trace_spans_start_time ON trace_spans (start_time)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_trace_spans_application ON trace_spans (application)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trace_spans_environment ON trace_spans (environment)"
    )

    # ── SLOs ──────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS slos (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            public_id UUID NOT NULL UNIQUE,
            monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            target_percentage DOUBLE PRECISION NOT NULL,
            window_days INTEGER NOT NULL DEFAULT 30,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_slos_organization_id ON slos (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_slos_monitor_id ON slos (monitor_id)")

    # ── Dashboard templates ───────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_templates (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            public_id UUID NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            widgets JSONB,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dashboard_templates_organization_id "
        "ON dashboard_templates (organization_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboard_templates")
    op.execute("DROP TABLE IF EXISTS slos")
    op.execute("DROP TABLE IF EXISTS trace_spans")
    op.execute("DROP TABLE IF EXISTS host_thresholds")
    op.execute("DROP TABLE IF EXISTS host_metrics")
    op.execute("DROP TABLE IF EXISTS log_entries")
    op.execute("DROP TABLE IF EXISTS api_keys")
    op.execute("DROP TABLE IF EXISTS maintenance_window_monitors")
    op.execute("DROP TABLE IF EXISTS maintenance_windows")
    op.execute("ALTER TABLE alerts ALTER COLUMN monitor_id SET NOT NULL")
    op.execute("ALTER TABLE check_results DROP COLUMN IF EXISTS meta")
    op.execute("DROP INDEX IF EXISTS ix_monitors_environment")
    op.execute(
        """
        ALTER TABLE monitors
            DROP COLUMN IF EXISTS ssl_issuer,
            DROP COLUMN IF EXISTS ssl_expires_at,
            DROP COLUMN IF EXISTS ssl_expiry_threshold_days,
            DROP COLUMN IF EXISTS expected_values,
            DROP COLUMN IF EXISTS record_type,
            DROP COLUMN IF EXISTS port,
            DROP COLUMN IF EXISTS expected_headers,
            DROP COLUMN IF EXISTS tags,
            DROP COLUMN IF EXISTS environment
        """
    )
