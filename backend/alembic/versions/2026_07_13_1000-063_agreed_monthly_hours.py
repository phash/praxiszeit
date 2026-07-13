"""#377 Baustein 2a: users.agreed_monthly_hours

Revision ID: 063_agreed_monthly_hours
Revises: 062_milog_flag
Create Date: 2026-07-13

Opt-in vereinbarte Monatsarbeitszeit (§ 2 Abs. 2 MiLoG-Arbeitszeitkonto). NULL =
wie bisher aus weekly_hours abgeleitet (× 13/3). users ist bereits tenant-scoped
(RLS + F-026); eine schlichte Spalte braucht keine Policy-Änderung.
"""
from alembic import op
import sqlalchemy as sa

revision = "063_agreed_monthly_hours"
down_revision = "062_milog_flag"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("agreed_monthly_hours", sa.Numeric(5, 1), nullable=True),
    )


def downgrade():
    op.drop_column("users", "agreed_monthly_hours")
