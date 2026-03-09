"""Add first and last work day to users

Revision ID: 024_first_last_work_day
Revises: 023_add_overtime
Create Date: 2026-03-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '024_first_last_work_day'
down_revision = '023_add_overtime'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('first_work_day', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('last_work_day', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_work_day')
    op.drop_column('users', 'first_work_day')
