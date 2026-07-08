"""#377 Minijob/MiLoG: users.milog_working_time_account

Revision ID: 062_milog_flag
Revises: 061_child_sick_fields
Create Date: 2026-07-08

Opt-in-Flag für die § 2 Abs. 2 MiLoG-Arbeitszeitkonto-Prüfungen (50 % + 12-Monats-
Ausgleich). users ist bereits tenant-scoped (RLS + F-026); eine schlichte Spalte
braucht keine Policy-Änderung.
"""
from alembic import op
import sqlalchemy as sa

revision = "062_milog_flag"
down_revision = "061_child_sick_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "milog_working_time_account",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("users", "milog_working_time_account")
