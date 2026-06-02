"""Add work-window columns (#201): users scheduled_start/end_<weekday>,
time_entries raw_start/end_time.

Alle nullable, kein Backfill → volle Abwärtskompatibilität. users ist
tenant-scoped, keine RLS-Änderung.

Revision ID: 048_add_work_window
Revises: 047_add_receives_closures
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = '048_add_work_window'
down_revision = '047_add_receives_closures'
branch_labels = None
depends_on = None

_WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday')


def upgrade() -> None:
    for wd in _WEEKDAYS:
        op.add_column('users', sa.Column(f'scheduled_start_{wd}', sa.Time(), nullable=True))
        op.add_column('users', sa.Column(f'scheduled_end_{wd}', sa.Time(), nullable=True))
    op.add_column('time_entries', sa.Column('raw_start_time', sa.Time(), nullable=True))
    op.add_column('time_entries', sa.Column('raw_end_time', sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column('time_entries', 'raw_end_time')
    op.drop_column('time_entries', 'raw_start_time')
    for wd in _WEEKDAYS:
        op.drop_column('users', f'scheduled_end_{wd}')
        op.drop_column('users', f'scheduled_start_{wd}')
