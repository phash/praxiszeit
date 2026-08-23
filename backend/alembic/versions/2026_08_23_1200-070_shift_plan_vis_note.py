"""#443: Schichtplan-Freigabe fuer Mitarbeitende + Hinweistext je Einteilung

``shift_plans.visible_to_employees``
    Bis hierher sahen Mitarbeitende ausschliesslich Plaene, die HEUTE gelten
    (``is_active`` oder das Datumsfenster deckt heute ab). Ein kuenftiger Plan
    liess sich damit nicht ankuendigen. Die Spalte ist die ausdrueckliche
    Freigabe: sie wirkt unabhaengig davon, ob der Plan schon gilt.

    Default ``false``: bestehende Installationen verhalten sich unveraendert,
    ein Entwurf wird nie durch die Migration oeffentlich.

``shift_slots.note``
    Freier Hinweistext je Einteilung ("Einarbeitung Azubi"). Reines
    Anzeigefeld — es fliesst in keine Pruefung und in keine Berechnung ein.
    ``Text`` statt ``String(n)``: der Text steht in keiner Spaltenbreite und
    eine Laengengrenze wuerde ohnehin am Rand (Pydantic ``max_length=500``)
    durchgesetzt, nicht in der Datenbank.

Beide Tabellen sind bereits mandantenbezogen mit RLS-Policy (Migration 053) —
reine Spalten-Ergaenzungen, keine Policy-Aenderung noetig.
"""
from alembic import op
import sqlalchemy as sa

revision = "070_shift_plan_vis_note"
down_revision = "069_weekly_hours_precision"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "shift_plans",
        sa.Column(
            "visible_to_employees",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("shift_slots", sa.Column("note", sa.Text(), nullable=True))


def downgrade():
    """Verlustfrei fuer alles, was das Alt-Modell kannte. Verloren gehen nur die
    Freigabe-Flags und die Hinweistexte — beides gab es vor dieser Migration
    nicht."""
    op.drop_column("shift_slots", "note")
    op.drop_column("shift_plans", "visible_to_employees")
