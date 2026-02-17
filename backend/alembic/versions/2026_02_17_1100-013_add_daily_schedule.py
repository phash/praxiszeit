"""add daily schedule to users

Revision ID: 013
Revises: 012
Create Date: 2026-02-17 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('use_daily_schedule', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('hours_monday', sa.Numeric(4, 2), nullable=True))
    op.add_column('users', sa.Column('hours_tuesday', sa.Numeric(4, 2), nullable=True))
    op.add_column('users', sa.Column('hours_wednesday', sa.Numeric(4, 2), nullable=True))
    op.add_column('users', sa.Column('hours_thursday', sa.Numeric(4, 2), nullable=True))
    op.add_column('users', sa.Column('hours_friday', sa.Numeric(4, 2), nullable=True))


def downgrade():
    op.drop_column('users', 'hours_friday')
    op.drop_column('users', 'hours_thursday')
    op.drop_column('users', 'hours_wednesday')
    op.drop_column('users', 'hours_tuesday')
    op.drop_column('users', 'hours_monday')
    op.drop_column('users', 'use_daily_schedule')
