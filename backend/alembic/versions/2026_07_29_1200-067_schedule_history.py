"""#431: working_hours_changes wird ein vollstaendiger Vertrags-Snapshot

Mitarbeitende mit individuellem Tagesplan hatten bisher keine Stundenhistorie —
ihr Tagessoll kam live aus users.hours_monday…friday, jede Aenderung verschob
still das Soll der gesamten Vergangenheit. Die Historien-Zeile traegt jetzt
Modus, Tageswerte und Arbeitstage mit.

Backfill: jede BESTEHENDE Zeile bekommt den heutigen Zustand ihres Users. Damit
bleibt das Verhalten nach der Migration byte-identisch — insbesondere im
Mischfall (Tagesplan-MA mit Alt-Zeilen aus der Zeit davor: diese Zeilen sind
heute wirkungslos und wuerden ohne Backfill schlagartig als gleichmaessige
Zeilen scharf geschaltet).
"""
from alembic import op
import sqlalchemy as sa

revision = "067_schedule_history"
down_revision = "066_vacation_days_decimal"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("working_hours_changes", sa.Column(
        "use_daily_schedule", sa.Boolean(), nullable=False, server_default="false"))
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        op.add_column("working_hours_changes", sa.Column(
            f"hours_{day}", sa.Numeric(4, 2), nullable=True))
    op.add_column("working_hours_changes", sa.Column(
        "work_days_per_week", sa.Integer(), nullable=True))

    # Backfill aus der zugehoerigen User-Zeile.
    op.execute("""
        UPDATE working_hours_changes AS w
        SET use_daily_schedule = u.use_daily_schedule,
            hours_monday = CASE WHEN u.use_daily_schedule THEN u.hours_monday END,
            hours_tuesday = CASE WHEN u.use_daily_schedule THEN u.hours_tuesday END,
            hours_wednesday = CASE WHEN u.use_daily_schedule THEN u.hours_wednesday END,
            hours_thursday = CASE WHEN u.use_daily_schedule THEN u.hours_thursday END,
            hours_friday = CASE WHEN u.use_daily_schedule THEN u.hours_friday END,
            work_days_per_week = u.work_days_per_week
        FROM users AS u
        WHERE w.user_id = u.id
    """)

    op.create_index(
        "ix_whc_user_effective_from",
        "working_hours_changes", ["user_id", "effective_from"],
    )


def downgrade():
    op.drop_index("ix_whc_user_effective_from", table_name="working_hours_changes")
    op.drop_column("working_hours_changes", "work_days_per_week")
    for day in ("friday", "thursday", "wednesday", "tuesday", "monday"):
        op.drop_column("working_hours_changes", f"hours_{day}")
    op.drop_column("working_hours_changes", "use_daily_schedule")
