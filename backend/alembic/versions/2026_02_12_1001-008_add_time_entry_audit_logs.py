"""add time_entry_audit_logs table

Revision ID: 008
Revises: 007
Create Date: 2026-02-12 10:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'time_entry_audit_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('time_entry_id', UUID(as_uuid=True), sa.ForeignKey('time_entries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('changed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('old_date', sa.Date(), nullable=True),
        sa.Column('old_start_time', sa.Time(), nullable=True),
        sa.Column('old_end_time', sa.Time(), nullable=True),
        sa.Column('old_break_minutes', sa.Integer(), nullable=True),
        sa.Column('old_note', sa.Text(), nullable=True),
        sa.Column('new_date', sa.Date(), nullable=True),
        sa.Column('new_start_time', sa.Time(), nullable=True),
        sa.Column('new_end_time', sa.Time(), nullable=True),
        sa.Column('new_break_minutes', sa.Integer(), nullable=True),
        sa.Column('new_note', sa.Text(), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='manual'),
        sa.Column('change_request_id', UUID(as_uuid=True), sa.ForeignKey('change_requests.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_time_entry_audit_logs_time_entry_id', 'time_entry_audit_logs', ['time_entry_id'])
    op.create_index('ix_time_entry_audit_logs_user_id', 'time_entry_audit_logs', ['user_id'])
    op.create_index('ix_time_entry_audit_logs_changed_by', 'time_entry_audit_logs', ['changed_by'])


def downgrade() -> None:
    op.drop_index('ix_time_entry_audit_logs_changed_by', table_name='time_entry_audit_logs')
    op.drop_index('ix_time_entry_audit_logs_user_id', table_name='time_entry_audit_logs')
    op.drop_index('ix_time_entry_audit_logs_time_entry_id', table_name='time_entry_audit_logs')
    op.drop_table('time_entry_audit_logs')
