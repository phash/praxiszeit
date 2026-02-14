"""make end_time nullable for clock-in/out

Revision ID: 009
Revises: 008
Create Date: 2026-02-14 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('time_entries', 'end_time',
                    existing_type=sa.Time(),
                    nullable=True)


def downgrade() -> None:
    # Close any open entries before making non-nullable
    op.execute("""
        UPDATE time_entries
        SET end_time = '23:59:00'
        WHERE end_time IS NULL
    """)
    op.alter_column('time_entries', 'end_time',
                    existing_type=sa.Time(),
                    nullable=False)
