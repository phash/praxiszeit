"""Add absence_type to vacation_requests table

Revision ID: 029_add_vacation_request_absence_type
Revises: 028_fix_review_findings
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = '029_add_vacation_request_absence_type'
down_revision = '028_fix_review_findings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'vacation_requests',
        sa.Column('absence_type', sa.String(20), nullable=False, server_default='vacation'),
    )


def downgrade() -> None:
    op.drop_column('vacation_requests', 'absence_type')
