"""#376 Kind-krank: tracks_child_sick_limit + child_sick_days_per_year

Revision ID: 061_child_sick_fields
Revises: 060_impersonation_sessions
Create Date: 2026-07-08

Adds:
- absence_reasons.tracks_child_sick_limit (bool, default false) — markiert den
  Kind-krank-Grund; zählt gegen das §45-SGB-V-Jahreslimit.
- users.child_sick_days_per_year (int, nullable) — persönlicher Jahresanspruch;
  NULL = Tenant-Default (Setting child_sick_days_default, sonst 15).

Beide Tabellen sind bereits tenant-scoped (RLS + F-026); eine schlichte Spalte
braucht keine Policy-Änderung.
"""
from alembic import op
import sqlalchemy as sa

revision = "061_child_sick_fields"
down_revision = "060_impersonation_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "absence_reasons",
        sa.Column(
            "tracks_child_sick_limit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("child_sick_days_per_year", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("users", "child_sick_days_per_year")
    op.drop_column("absence_reasons", "tracks_child_sick_limit")
