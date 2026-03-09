"""Add overtime absence type

Revision ID: 023_add_overtime
Revises: 022_add_vacation_requests
Create Date: 2026-03-09 15:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '023_add_overtime'
down_revision = '022_add_vacation_requests'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE absencetype ADD VALUE IF NOT EXISTS 'OVERTIME'")


def downgrade() -> None:
    pass  # PostgreSQL doesn't support removing enum values
