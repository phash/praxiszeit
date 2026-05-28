"""Add is_custom + source to public_holidays for admin-managed local holidays.

Admins can add regional/local holidays (Schützenfest, Karneval, …) that the
``workalendar`` Bundesland logic does not cover. Two columns distinguish them:

* ``is_custom`` — TRUE for admin-created holidays, FALSE for workalendar-seeded.
* ``source``    — provenance marker: 'workalendar' (auto-seeded, replaced on a
  Bundesland resync) or 'admin' (manually maintained, survives a resync).

The Bundesland-change resync deletes/regenerates ONLY ``source='workalendar'``
rows, so admin holidays persist. Existing rows are all workalendar-seeded, so
the column defaults ('workalendar' / false) backfill them correctly.

Revision ID: 040_custom_holiday_fields
Revises: 039_user_onboarding
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa


revision = '040_custom_holiday_fields'
down_revision = '039_user_onboarding'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'public_holidays',
        sa.Column(
            'is_custom',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        'public_holidays',
        sa.Column(
            'source',
            sa.String(length=20),
            nullable=False,
            server_default='workalendar',
        ),
    )


def downgrade() -> None:
    op.drop_column('public_holidays', 'source')
    op.drop_column('public_holidays', 'is_custom')
