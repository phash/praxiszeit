"""Add last_totp_counter for replay protection

A TOTP code is valid for ~30s (plus the one adjacent window). Without
persisting which counter we last accepted, an attacker who captures a live
code via shoulder-surf / phishing can replay it within ~60s against the
login endpoint. `last_totp_counter` stores the highest counter value we
have already accepted for a user; verify_totp rejects any code whose
counter is <= that value.

Revision ID: 032_totp_replay
Revises: 031_composite_indexes
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa


revision = '032_totp_replay'
down_revision = '031_composite_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_totp_counter', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_totp_counter')
