"""Make monitors.url nullable for heartbeat monitors.

Revision ID: 20261113_monitor_url_nullable
Revises: 20261113_observability
Create Date: 2026-11-13

The ORM has always declared url as nullable (heartbeat monitors are push-based
and have no target URL), but databases bootstrapped from earlier model states
carry a NOT NULL constraint that breaks HEARTBEAT monitor creation.
"""

from __future__ import annotations

from alembic import op

revision = "20261113_monitor_url_nullable"
down_revision = "20261113_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE monitors ALTER COLUMN url DROP NOT NULL")


def downgrade() -> None:
    op.execute("DELETE FROM monitors WHERE url IS NULL")
    op.execute("ALTER TABLE monitors ALTER COLUMN url SET NOT NULL")
