"""add_sunday_exception_reason_and_arbzg_exempt

Revision ID: 3ff6a4b5b9cd
Revises: 05d89711f916
Create Date: 2026-02-28 00:10:40.031390

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3ff6a4b5b9cd'
down_revision = '05d89711f916'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # §10 ArbZG: optional exception reason on time entries (Sonn-/Feiertagsarbeit)
    op.add_column('time_entries', sa.Column('sunday_exception_reason', sa.Text(), nullable=True))
    # §18 ArbZG: exempt leitende Angestellte from ArbZG checks
    op.add_column('users', sa.Column('exempt_from_arbzg', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('time_entries', 'sunday_exception_reason')
    op.drop_column('users', 'exempt_from_arbzg')
