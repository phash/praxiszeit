"""add change_requests table

Revision ID: 007
Revises: 006
Create Date: 2026-02-12 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'change_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_type', sa.Enum('create', 'update', 'delete', name='changerequesttype'), nullable=False),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='changerequeststatus'), nullable=False, server_default='pending'),
        sa.Column('time_entry_id', UUID(as_uuid=True), sa.ForeignKey('time_entries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('proposed_date', sa.Date(), nullable=True),
        sa.Column('proposed_start_time', sa.Time(), nullable=True),
        sa.Column('proposed_end_time', sa.Time(), nullable=True),
        sa.Column('proposed_break_minutes', sa.Integer(), nullable=True),
        sa.Column('proposed_note', sa.Text(), nullable=True),
        sa.Column('original_date', sa.Date(), nullable=True),
        sa.Column('original_start_time', sa.Time(), nullable=True),
        sa.Column('original_end_time', sa.Time(), nullable=True),
        sa.Column('original_break_minutes', sa.Integer(), nullable=True),
        sa.Column('original_note', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('reviewed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_change_requests_user_id', 'change_requests', ['user_id'])
    op.create_index('ix_change_requests_status', 'change_requests', ['status'])
    op.create_index('ix_change_requests_time_entry_id', 'change_requests', ['time_entry_id'])


def downgrade() -> None:
    op.drop_index('ix_change_requests_time_entry_id', table_name='change_requests')
    op.drop_index('ix_change_requests_status', table_name='change_requests')
    op.drop_index('ix_change_requests_user_id', table_name='change_requests')
    op.drop_table('change_requests')
    op.execute("DROP TYPE IF EXISTS changerequesttype")
    op.execute("DROP TYPE IF EXISTS changerequeststatus")
