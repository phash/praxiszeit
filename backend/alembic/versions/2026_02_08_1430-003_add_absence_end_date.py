"""add end_date to absences

Revision ID: 003
Revises: 002
Create Date: 2026-02-08 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add end_date column (nullable for backward compatibility)
    op.add_column('absences', sa.Column('end_date', sa.Date(), nullable=True))
    # Add index for better query performance
    op.create_index(op.f('ix_absences_end_date'), 'absences', ['end_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_absences_end_date'), table_name='absences')
    op.drop_column('absences', 'end_date')
