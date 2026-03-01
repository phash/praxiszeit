"""add_vacation_requests

Revision ID: 022_add_vacation_requests
Revises: 021_add_system_settings
Create Date: 2026-03-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '022_add_vacation_requests'
down_revision = '021_add_system_settings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'vacation_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('hours', sa.Numeric(5, 2), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('reviewed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_vacation_requests_user_id', 'vacation_requests', ['user_id'])
    op.create_index('ix_vacation_requests_status', 'vacation_requests', ['status'])
    op.create_index('ix_vacation_requests_date', 'vacation_requests', ['date'])


def downgrade() -> None:
    op.drop_index('ix_vacation_requests_date', 'vacation_requests')
    op.drop_index('ix_vacation_requests_status', 'vacation_requests')
    op.drop_index('ix_vacation_requests_user_id', 'vacation_requests')
    op.drop_table('vacation_requests')
