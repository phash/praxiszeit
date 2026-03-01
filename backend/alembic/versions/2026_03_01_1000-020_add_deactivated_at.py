"""add_deactivated_at

Revision ID: 020_add_deactivated_at
Revises: 019_add_totp_2fa
Create Date: 2026-03-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '020_add_deactivated_at'
down_revision = '019_add_totp_2fa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 14-Tage-Grace-Period: Zeitstempel der Deaktivierung für DSGVO-Anonymisierungssperre
    op.add_column('users', sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'deactivated_at')
