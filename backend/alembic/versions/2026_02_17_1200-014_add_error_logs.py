"""add error logs table

Revision ID: 014
Revises: 013
Create Date: 2026-02-17 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'error_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('level', sa.String(20), nullable=False, index=True),          # 'error', 'warning', 'critical'
        sa.Column('logger', sa.String(200), nullable=False),                     # logger name
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('traceback', sa.Text, nullable=True),
        sa.Column('path', sa.String(500), nullable=True),                        # request path
        sa.Column('method', sa.String(10), nullable=True),                       # GET, POST, etc.
        sa.Column('status_code', sa.Integer, nullable=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fingerprint', sa.String(64), nullable=False, index=True),     # SHA256 for deduplication
        sa.Column('count', sa.Integer, nullable=False, server_default='1'),      # aggregation count
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('status', sa.String(20), nullable=False, server_default="'open'"),  # 'open', 'ignored', 'resolved'
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('github_issue_url', sa.String(500), nullable=True),
    )
    op.create_index('ix_error_logs_status', 'error_logs', ['status'])
    op.create_index('ix_error_logs_last_seen', 'error_logs', ['last_seen'])


def downgrade():
    op.drop_table('error_logs')
