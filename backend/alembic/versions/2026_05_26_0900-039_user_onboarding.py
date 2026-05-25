"""Add users.onboarding_completed_at for the first-login onboarding tour.

NULL = onboarding not yet seen -> the frontend shows a role-specific welcome
modal on first login, then POSTs /auth/onboarding/complete to set the
timestamp (so it does not reappear on other devices / future logins).

Existing users are backfilled to "completed" (now) so upgrading an install
that has been in use for months does not suddenly interrupt everyone — only
genuinely new accounts (incl. the bootstrap admin on a fresh install, which is
created after migrations run) start with NULL and see the onboarding.

Revision ID: 039_user_onboarding
Revises: 038_vr_last_modified
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa


revision = '039_user_onboarding'
down_revision = '038_vr_last_modified'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('onboarding_completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Bestandsnutzer nicht mit dem Onboarding belaestigen -> als "gesehen" markieren.
    op.execute("UPDATE users SET onboarding_completed_at = now() WHERE onboarding_completed_at IS NULL")


def downgrade() -> None:
    op.drop_column('users', 'onboarding_completed_at')
