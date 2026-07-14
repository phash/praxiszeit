"""#377 Baustein 2b: users.use_fixed_monthly_target

Revision ID: 065_fixed_monthly_target
Revises: 064_carryover_vac_prec
Create Date: 2026-07-14

Opt-in: festes Monats-Soll (= agreed_monthly_hours) statt Per-Tag-Summe.
Default false → alle Bestands-MA unverändert. users ist bereits tenant-scoped.
"""
from alembic import op
import sqlalchemy as sa

revision = "065_fixed_monthly_target"
down_revision = "064_carryover_vac_prec"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("use_fixed_monthly_target", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade():
    op.drop_column("users", "use_fixed_monthly_target")
