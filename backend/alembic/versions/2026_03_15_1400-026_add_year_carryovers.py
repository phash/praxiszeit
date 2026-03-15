"""Add year_carryovers table for overtime and vacation carryover from previous year

Revision ID: 026_add_year_carryovers
Revises: 025_add_profile_picture
Create Date: 2026-03-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '026_add_year_carryovers'
down_revision = '025_add_profile_picture'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'year_carryovers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('overtime_hours', sa.Numeric(8, 2), nullable=False, server_default='0'),
        sa.Column('vacation_days', sa.Numeric(4, 1), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'year', name='uq_year_carryover_user_year'),
    )


def downgrade() -> None:
    op.drop_table('year_carryovers')
