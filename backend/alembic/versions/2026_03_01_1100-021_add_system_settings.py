"""add_system_settings

Revision ID: 021_add_system_settings
Revises: 020_add_deactivated_at
Create Date: 2026-03-01 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '021_add_system_settings'
down_revision = '020_add_deactivated_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(100), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "INSERT INTO system_settings (key, value, description) VALUES "
        "('vacation_approval_required', 'false', 'Urlaubsantraege erfordern Admin-Genehmigung')"
    )


def downgrade() -> None:
    op.drop_table('system_settings')
