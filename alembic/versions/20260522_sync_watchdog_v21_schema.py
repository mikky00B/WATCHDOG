"""Sync WATCHDOG v2.1 schema additions.

Revision ID: 20260522_v21
Revises:
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op

revision = "20260522_v21"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE monitors
            ADD COLUMN IF NOT EXISTS organization_id INTEGER,
            ADD COLUMN IF NOT EXISTS client_id INTEGER,
            ADD COLUMN IF NOT EXISTS heartbeat_key VARCHAR(255),
            ADD COLUMN IF NOT EXISTS http_method VARCHAR(20) NOT NULL DEFAULT 'GET',
            ADD COLUMN IF NOT EXISTS expected_status_code INTEGER,
            ADD COLUMN IF NOT EXISTS expected_response_text TEXT,
            ADD COLUMN IF NOT EXISTS expected_json JSON,
            ADD COLUMN IF NOT EXISTS request_headers JSON,
            ADD COLUMN IF NOT EXISTS request_body TEXT,
            ADD COLUMN IF NOT EXISTS response_time_threshold_ms INTEGER,
            ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
            ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS consecutive_successes INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS next_check_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE check_results
            ADD COLUMN IF NOT EXISTS organization_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE alerts
            ADD COLUMN IF NOT EXISTS organization_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE heartbeats
            ADD COLUMN IF NOT EXISTS organization_id INTEGER
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_monitors_organization_id ON monitors (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_monitors_client_id ON monitors (client_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_monitors_heartbeat_key ON monitors (heartbeat_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_monitors_next_check_at ON monitors (next_check_at)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_check_results_organization_id ON check_results (organization_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_organization_id ON alerts (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_heartbeats_organization_id ON heartbeats (organization_id)")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_monitors_organization_id'
            ) THEN
                ALTER TABLE monitors
                    ADD CONSTRAINT fk_monitors_organization_id
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_monitors_client_id'
            ) THEN
                ALTER TABLE monitors
                    ADD CONSTRAINT fk_monitors_client_id
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_check_results_organization_id'
            ) THEN
                ALTER TABLE check_results
                    ADD CONSTRAINT fk_check_results_organization_id
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_alerts_organization_id'
            ) THEN
                ALTER TABLE alerts
                    ADD CONSTRAINT fk_alerts_organization_id
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_heartbeats_organization_id'
            ) THEN
                ALTER TABLE heartbeats
                    ADD CONSTRAINT fk_heartbeats_organization_id
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE heartbeats DROP COLUMN IF EXISTS organization_id")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS organization_id")
    op.execute("ALTER TABLE check_results DROP COLUMN IF EXISTS organization_id")
    op.execute(
        """
        ALTER TABLE monitors
            DROP COLUMN IF EXISTS organization_id,
            DROP COLUMN IF EXISTS client_id,
            DROP COLUMN IF EXISTS heartbeat_key,
            DROP COLUMN IF EXISTS http_method,
            DROP COLUMN IF EXISTS expected_status_code,
            DROP COLUMN IF EXISTS expected_response_text,
            DROP COLUMN IF EXISTS expected_json,
            DROP COLUMN IF EXISTS request_headers,
            DROP COLUMN IF EXISTS request_body,
            DROP COLUMN IF EXISTS response_time_threshold_ms,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS consecutive_failures,
            DROP COLUMN IF EXISTS consecutive_successes,
            DROP COLUMN IF EXISTS next_check_at
        """
    )
