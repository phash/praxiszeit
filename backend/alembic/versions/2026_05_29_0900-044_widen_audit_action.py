"""Widen time_entry_audit_logs.action from VARCHAR(20) to VARCHAR(40).

The 20-char limit dated back to when only short actions existed
(``create`` / ``update`` / ``delete``). Newer code paths emit
``arbzg_superadmin_export`` (23 chars, superadmin §16 emergency export) and
``license_readonly_mode_entered`` (29 chars, license read-only audit), both of
which overflow varchar(20) → ``StringDataRightTruncation`` → 500 on the
§16 export and a silently-dropped read-only audit row. SQLite (test DB) ignores
varchar length, so CI never caught it. Widening to 40 mirrors migration 037
(``source``) and leaves headroom for future markers.

Revision ID: 044_widen_audit_action
Revises: 043_break_waiver
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


revision = '044_widen_audit_action'
down_revision = '043_break_waiver'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'time_entry_audit_logs',
        'action',
        existing_type=sa.String(length=20),
        type_=sa.String(length=40),
        existing_nullable=False,
        existing_server_default=None,
    )


def downgrade() -> None:
    # Best-effort — will fail if any row already holds a >20-char value.
    op.alter_column(
        'time_entry_audit_logs',
        'action',
        existing_type=sa.String(length=40),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
