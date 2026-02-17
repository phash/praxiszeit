"""add_hidden_to_users

Revision ID: 015_add_hidden_to_users
Revises: 014_add_error_logs
Create Date: 2026-02-17 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('users', 'is_hidden')
