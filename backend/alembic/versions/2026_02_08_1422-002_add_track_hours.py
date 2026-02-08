"""add track_hours to users

Revision ID: 002
Revises: 001
Create Date: 2026-02-08 14:22:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add track_hours column with default True
    op.add_column('users', sa.Column('track_hours', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    op.drop_column('users', 'track_hours')
