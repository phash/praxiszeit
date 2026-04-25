"""Widen time_entry_audit_logs.source from VARCHAR(20) to VARCHAR(40).

The 20-char limit was set when only short source markers existed (``manual``,
``import``, ``change_request``). Newer code paths emit ``vacation_request_cancel``
(24 chars), which crashed every approved-future-vacation-request cancellation
with ``StringDataRightTruncation`` → 500. Widening to 40 leaves headroom for
future markers without forcing another migration.

Revision ID: 037_widen_audit_source
Revises: 036_tenant_lifecycle
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa


revision = '037_widen_audit_source'
down_revision = '036_tenant_lifecycle'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'time_entry_audit_logs',
        'source',
        existing_type=sa.String(length=20),
        type_=sa.String(length=40),
        existing_nullable=False,
        existing_server_default=None,
    )


def downgrade() -> None:
    # Best-effort — will fail if any row already holds a >20-char value.
    op.alter_column(
        'time_entry_audit_logs',
        'source',
        existing_type=sa.String(length=40),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
