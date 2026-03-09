"""Add profile picture to users

Revision ID: 025_add_profile_picture
Revises: 024_first_last_work_day
Create Date: 2026-03-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '025_add_profile_picture'
down_revision = '024_first_last_work_day'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('profile_picture', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'profile_picture')
