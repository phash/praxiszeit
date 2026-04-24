"""Stripe webhook idempotency cache (Phase 4 / Issue #95)

Stripe promises at-least-once delivery. We de-duplicate by storing every
event id we've already processed; the webhook endpoint checks this table
before acting on an event.

Revision ID: 035_stripe_events
Revises: 034_signup_tokens
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '035_stripe_events'
down_revision = '034_signup_tokens'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'stripe_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', sa.String(255), unique=True, nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        # Store the raw event payload for debugging / replay; trimmed by the
        # app layer to a reasonable size before insert.
        sa.Column('payload_excerpt', sa.Text(), nullable=True),
    )
    op.create_index('ix_stripe_events_event_type', 'stripe_events', ['event_type'])
    op.create_index('ix_stripe_events_tenant_id', 'stripe_events', ['tenant_id'])
    op.create_index('ix_stripe_events_processed_at', 'stripe_events', ['processed_at'])


def downgrade() -> None:
    op.drop_index('ix_stripe_events_processed_at', 'stripe_events')
    op.drop_index('ix_stripe_events_tenant_id', 'stripe_events')
    op.drop_index('ix_stripe_events_event_type', 'stripe_events')
    op.drop_table('stripe_events')
