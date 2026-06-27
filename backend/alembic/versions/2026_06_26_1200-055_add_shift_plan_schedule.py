"""Add shift_plans.active_from_date / active_until_date (KW-Planung, #305 M2).

Optional date window for automatic activation across the year. Additive,
nullable, no backfill — existing plans keep is_active behaviour.

Revision ID: 055_add_shift_plan_schedule
Revises: 054_add_workstation_quals
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa


revision = '055_add_shift_plan_schedule'
down_revision = '054_add_workstation_quals'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('shift_plans', sa.Column('active_from_date', sa.Date(), nullable=True))
    op.add_column('shift_plans', sa.Column('active_until_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('shift_plans', 'active_until_date')
    op.drop_column('shift_plans', 'active_from_date')
