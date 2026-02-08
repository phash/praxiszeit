"""add user calendar color

Revision ID: 004
Revises: 003
Create Date: 2026-02-08 21:54

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add calendar_color column with default pastel blue
    op.add_column('users', sa.Column('calendar_color', sa.String(length=7), nullable=False, server_default='#93C5FD'))


def downgrade() -> None:
    op.drop_column('users', 'calendar_color')
