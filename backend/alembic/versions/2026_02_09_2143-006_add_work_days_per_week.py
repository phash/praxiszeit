"""add work_days_per_week to users

Revision ID: 006
Revises: 005
Create Date: 2026-02-09 21:43:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add work_days_per_week column with default 5 for existing users
    op.add_column('users', sa.Column(
        'work_days_per_week',
        sa.Integer(),
        nullable=False,
        server_default='5'
    ))


def downgrade() -> None:
    # Remove work_days_per_week column
    op.drop_column('users', 'work_days_per_week')
