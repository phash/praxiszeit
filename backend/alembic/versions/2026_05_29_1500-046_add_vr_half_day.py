"""Add vacation_requests.half_day (#167 — halbe Urlaubstage im Antrags-Workflow).

Nullable Boolean, Default false. Markiert einen Urlaubsantrag als halben Tag;
bei Genehmigung wird die Abwesenheit mit 0,5 × Tagessoll gebucht.

Revision ID: 046_add_vr_half_day
Revises: 045_add_user_department
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


revision = '046_add_vr_half_day'
down_revision = '045_add_user_department'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'vacation_requests',
        sa.Column('half_day', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('vacation_requests', 'half_day')
