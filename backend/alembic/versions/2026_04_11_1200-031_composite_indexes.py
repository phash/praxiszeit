"""Add (tenant_id, user_id, date) composite indexes for hot report queries

F-031 (Performance): Every reporting and dashboard query has the shape
``WHERE user_id = ? AND date BETWEEN ? AND ?`` with the implicit
``tenant_id = ?`` pushed in by RLS. Before this migration Postgres has to
bitmap-AND two single-column indexes (ix_*_user_id + ix_*_date) on every
query. A single composite index matches all three predicates in order and
eliminates the bitmap merge step.

Revision ID: 031_composite_indexes
Revises: 030_absence_times_cr
Create Date: 2026-04-11
"""
from alembic import op


revision = '031_composite_indexes'
down_revision = '030_absence_times_cr'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite on time_entries
    op.create_index(
        'ix_time_entries_tenant_user_date',
        'time_entries',
        ['tenant_id', 'user_id', 'date'],
    )

    # Composite on absences
    op.create_index(
        'ix_absences_tenant_user_date',
        'absences',
        ['tenant_id', 'user_id', 'date'],
    )

    # Composite on working_hours_changes: the get_weekly_hours_for_date()
    # hot path runs ORDER BY effective_from DESC LIMIT 1 for a user.
    op.create_index(
        'ix_wh_changes_user_effective_from',
        'working_hours_changes',
        ['user_id', 'effective_from'],
    )


def downgrade() -> None:
    op.drop_index('ix_wh_changes_user_effective_from', table_name='working_hours_changes')
    op.drop_index('ix_absences_tenant_user_date', table_name='absences')
    op.drop_index('ix_time_entries_tenant_user_date', table_name='time_entries')
