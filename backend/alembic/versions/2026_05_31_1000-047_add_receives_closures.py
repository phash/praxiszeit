"""Add users.receives_company_closures (#189).

Per-user flag controlling whether a user gets Betriebsferien (company closure)
absences. Default True, backfilled True for all existing users.

Replaces the old hard ``role != ADMIN`` filter in ``company_closures`` so that
an admin who is also a (leitender) Angestellter — i.e. tracks time / has a
vacation account but holds admin rights for personnel work — still receives the
closure. Pure administration accounts that should NOT get closures can opt out
by unsetting the flag.

NOT NULL with server_default true → safe online add, every existing user keeps
the prior behaviour (all non-admins received closures; admins who previously
did not are now included by default, which is the intended fix).

Revision ID: 047_add_receives_closures
Revises: 046_add_vr_half_day
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa


revision = '047_add_receives_closures'
down_revision = '046_add_vr_half_day'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'receives_company_closures',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'receives_company_closures')
