"""Vertragsverlauf (Teil A): Urlaub, Stundenzaehlung und MiLoG im Snapshot.

Jede ``working_hours_changes``-Zeile ist ein Vertrags-Snapshot (#431). Ab hier
tragen die Zeilen auch ``vacation_days``, ``track_hours``,
``milog_working_time_account``, ``agreed_monthly_hours`` und
``use_fixed_monthly_target``.

Backfill: JEDE Bestandszeile bekommt die heutigen Werte der User-Zeile. Bisher
wirkten diese Felder live und fuer alle Datumsangaben gleich - mit identischen
Werten in allen Zeilen aendert sich also kein vergangenes Ergebnis (Prinzip wie
067/073). Danach sind vier der fuenf Spalten NOT NULL; ``agreed_monthly_hours``
bleibt nullable (NULL = aus ``weekly_hours`` abgeleitet, nie Rueckfall auf
``users``).

Downgrade: die fuenf Spalten werden verworfen (Historie der Felder geht
verloren, die User-Zeile behaelt den aktuellen Wert).
"""
from alembic import op
import sqlalchemy as sa

revision = "075_contract_history"
down_revision = "074_reduced_days"
branch_labels = None
depends_on = None

TABLE = "working_hours_changes"
NOT_NULL = ("vacation_days", "track_hours", "milog_working_time_account", "use_fixed_monthly_target")


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("vacation_days", sa.Numeric(4, 1), nullable=True))
    op.add_column(TABLE, sa.Column("track_hours", sa.Boolean(), nullable=True))
    op.add_column(TABLE, sa.Column("milog_working_time_account", sa.Boolean(), nullable=True))
    op.add_column(TABLE, sa.Column("agreed_monthly_hours", sa.Numeric(5, 1), nullable=True))
    op.add_column(TABLE, sa.Column("use_fixed_monthly_target", sa.Boolean(), nullable=True))

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        # FORCE RLS: sonst trifft der Backfill still 0 Zeilen (Muster 073)
        conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))
    result = conn.execute(sa.text(
        "UPDATE working_hours_changes SET "
        "vacation_days = (SELECT u.vacation_days FROM users u WHERE u.id = working_hours_changes.user_id), "
        "track_hours = (SELECT u.track_hours FROM users u WHERE u.id = working_hours_changes.user_id), "
        "milog_working_time_account = (SELECT u.milog_working_time_account FROM users u "
        "WHERE u.id = working_hours_changes.user_id), "
        "agreed_monthly_hours = (SELECT u.agreed_monthly_hours FROM users u "
        "WHERE u.id = working_hours_changes.user_id), "
        "use_fixed_monthly_target = (SELECT u.use_fixed_monthly_target FROM users u "
        "WHERE u.id = working_hours_changes.user_id)"
    ))
    count = result.rowcount

    for name in NOT_NULL:
        op.alter_column(TABLE, name, nullable=False)

    try:
        print(f"075: {count} Verlaufszeilen übernommen")
    except UnicodeEncodeError:
        print(f"075: {count} Verlaufszeilen uebernommen")


def downgrade() -> None:
    for name in ("use_fixed_monthly_target", "agreed_monthly_hours",
                 "milog_working_time_account", "track_hours", "vacation_days"):
        op.drop_column(TABLE, name)
