"""Add absences.half_day for day-based vacation consumption (#205).

The vacation budget is counted per the Tagesprinzip (§3 BUrlG): full day = 1.0,
half day = 0.5. Until now the consumption was derived as ``Absence.hours / live
daily_target``, which drifts when a WorkingHoursChange retroactively alters the
daily target of an already-booked day, and the untracked branch
(track_hours=False, hours=0) could not tell a half day from a full one at all.

We persist the booking-time intent (``half_day``) so consumption is day-based and
WorkingHoursChange-stable. Column is NULLABLE on purpose: rows written BEFORE this
change keep ``NULL`` and are counted with the legacy hours-based logic (no
regression / no unreliable inference); only NEW rows carry True/False and use the
day-based count.

Revision ID: 052_add_absence_half_day
Revises: 051_add_audit_row_hash
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '052_add_absence_half_day'
down_revision = '051_add_audit_row_hash'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'absences',
        sa.Column('half_day', sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('absences', 'half_day')
