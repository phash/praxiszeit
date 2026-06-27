"""Add change_requests.proposed_reason_id (#312 — custom reason via CR workflow).

Lets the absence change-request workflow carry an optional custom absence reason
through to approval. Additive, nullable.

Revision ID: 057_add_cr_proposed_reason
Revises: 056_add_absence_reasons
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '057_add_cr_proposed_reason'
down_revision = '056_add_absence_reasons'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('change_requests', sa.Column('proposed_reason_id', postgresql.UUID(as_uuid=True),
                                               sa.ForeignKey('absence_reasons.id', ondelete='SET NULL'),
                                               nullable=True))
    op.create_index('ix_change_requests_proposed_reason_id', 'change_requests', ['proposed_reason_id'])


def downgrade() -> None:
    op.drop_index('ix_change_requests_proposed_reason_id', table_name='change_requests')
    op.drop_column('change_requests', 'proposed_reason_id')
