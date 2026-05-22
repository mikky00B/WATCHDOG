"""Add user email verification fields.

Revision ID: 20260522_email_verification
Revises: 20260522_v21
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op

revision = "20260522_email_verification"
down_revision = "20260522_v21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS email_verification_code_hash VARCHAR(128),
            ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        UPDATE users
        SET is_verified = TRUE,
            verified_at = COALESCE(verified_at, updated_at, now())
        WHERE is_verified = FALSE
          AND email_verification_code_hash IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
            DROP COLUMN IF EXISTS verified_at,
            DROP COLUMN IF EXISTS email_verification_expires_at,
            DROP COLUMN IF EXISTS email_verification_code_hash
        """
    )
