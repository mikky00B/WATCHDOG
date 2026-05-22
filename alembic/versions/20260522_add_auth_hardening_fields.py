"""Add auth hardening fields and sessions.

Revision ID: 20260522_auth_hardening
Revises: 20260522_email_verification
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op

revision = "20260522_auth_hardening"
down_revision = "20260522_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS email_verification_failed_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS password_reset_code_hash VARCHAR(128),
            ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN IF NOT EXISTS password_reset_failed_attempts INTEGER NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id SERIAL PRIMARY KEY,
            token_hash VARCHAR(128) NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            revoked_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_sessions_token_hash ON auth_sessions (token_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_id ON auth_sessions (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_sessions")
    op.execute(
        """
        ALTER TABLE users
            DROP COLUMN IF EXISTS password_reset_failed_attempts,
            DROP COLUMN IF EXISTS password_reset_expires_at,
            DROP COLUMN IF EXISTS password_reset_code_hash,
            DROP COLUMN IF EXISTS email_verification_failed_attempts
        """
    )
