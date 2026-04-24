"""Tenant lifecycle: scheduled suspend + deletion-request timestamps (Phase 6 / #97)

Revision ID: 036_tenant_lifecycle
Revises: 035_stripe_events
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '036_tenant_lifecycle'
down_revision = '035_stripe_events'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Suspend scheduling: admin self-service → 7d grace, then cron applies it.
    op.add_column('tenants', sa.Column('scheduled_suspend_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tenants', sa.Column('scheduled_suspend_by', postgresql.UUID(as_uuid=True), nullable=True))

    # Deletion request: admin sets → cron anonymizes after 30d grace.
    op.add_column('tenants', sa.Column('deletion_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tenants', sa.Column('deletion_requested_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('tenants', sa.Column('anonymized_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('tenants', 'anonymized_at')
    op.drop_column('tenants', 'deletion_requested_by')
    op.drop_column('tenants', 'deletion_requested_at')
    op.drop_column('tenants', 'scheduled_suspend_by')
    op.drop_column('tenants', 'scheduled_suspend_at')
