"""Add users.department (optional free-text Abteilung/Bereich, #162).

Nullable VARCHAR(100). No backfill, no RLS change — ``users`` is already
tenant-scoped, this is just an additional optional attribute used for grouping
and filtering in absence overviews.

Revision ID: 045_add_user_department
Revises: 044_widen_audit_action
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


revision = '045_add_user_department'
down_revision = '044_widen_audit_action'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('department', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'department')
