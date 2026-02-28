"""add_totp_2fa

Revision ID: 019_add_totp_2fa
Revises: 017_add_is_night_worker
Create Date: 2026-02-28 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '019_add_totp_2fa'
down_revision = '017_add_is_night_worker'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # F-019: TOTP-basierte 2FA für alle Benutzer
    op.add_column('users', sa.Column('totp_secret', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(),
                  nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
