"""Add year_carryovers.source (Fix #7 — distinguish year-closing vs manual).

delete_year_closing must only remove carryovers it created (source='year_closing')
and leave admin-entered manual carryovers (source='manual') intact. Additive,
NOT NULL with server_default so existing rows backfill to 'year_closing'.

Revision ID: 058_carryover_source
Revises: 057_add_cr_proposed_reason
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa


revision = '058_carryover_source'
down_revision = '057_add_cr_proposed_reason'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'year_carryovers',
        sa.Column('source', sa.String(length=20), nullable=False,
                  server_default='year_closing'),
    )
    # Existing rows predate manual/year-closing distinction → all treated as
    # year-closing (backfilled by the server_default). Keep the server_default
    # so future raw inserts stay covered.


def downgrade() -> None:
    op.drop_column('year_carryovers', 'source')
