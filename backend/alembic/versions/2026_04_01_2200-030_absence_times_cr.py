"""Add start_time/end_time to absences, extend change_requests for absence support

Revision ID: 030_absence_times_cr
Revises: 029_add_vacation_request_absence_type
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = '030_absence_times_cr'
down_revision = '029_add_vacation_request_absence_type'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- absences: optional start_time / end_time ---
    op.add_column('absences', sa.Column('start_time', sa.Time(), nullable=True))
    op.add_column('absences', sa.Column('end_time', sa.Time(), nullable=True))

    # --- change_requests: entry_kind discriminator ---
    op.add_column(
        'change_requests',
        sa.Column('entry_kind', sa.String(20), nullable=False, server_default='time_entry'),
    )

    # --- change_requests: absence reference ---
    op.add_column(
        'change_requests',
        sa.Column('absence_id', PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_change_requests_absence_id',
        'change_requests',
        'absences',
        ['absence_id'],
        ['id'],
    )
    op.create_index('ix_change_requests_absence_id', 'change_requests', ['absence_id'])

    # --- change_requests: proposed / original absence fields ---
    op.add_column(
        'change_requests',
        sa.Column('proposed_absence_type', sa.String(20), nullable=True),
    )
    op.add_column(
        'change_requests',
        sa.Column('proposed_absence_hours', sa.Numeric(4, 2), nullable=True),
    )
    op.add_column(
        'change_requests',
        sa.Column('original_absence_type', sa.String(20), nullable=True),
    )
    op.add_column(
        'change_requests',
        sa.Column('original_absence_hours', sa.Numeric(4, 2), nullable=True),
    )

    # Backfill: ensure every existing row has the default
    op.execute("UPDATE change_requests SET entry_kind = 'time_entry' WHERE entry_kind IS NULL")


def downgrade() -> None:
    # --- change_requests: drop absence fields ---
    op.drop_column('change_requests', 'original_absence_hours')
    op.drop_column('change_requests', 'original_absence_type')
    op.drop_column('change_requests', 'proposed_absence_hours')
    op.drop_column('change_requests', 'proposed_absence_type')

    op.drop_index('ix_change_requests_absence_id', table_name='change_requests')
    op.drop_constraint('fk_change_requests_absence_id', 'change_requests', type_='foreignkey')
    op.drop_column('change_requests', 'absence_id')

    op.drop_column('change_requests', 'entry_kind')

    # --- absences: drop time columns ---
    op.drop_column('absences', 'end_time')
    op.drop_column('absences', 'start_time')
