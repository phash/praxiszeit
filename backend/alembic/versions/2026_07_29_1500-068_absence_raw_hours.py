"""Task 15: absences.raw_hours — der unangetastete Rohwert einer Abwesenheit

``calculation_service.retarget_absence_hours`` ueberschreibt ``absences.hours``
in place, sobald sich das Tagessoll durch eine Wochenstunden-/Tagesplan-Aenderung
verschiebt. Der vorherige Wert war danach unwiederbringlich weg — stellte sich
die Rueckrechnung als falsch heraus, gab es keinen Weg zurueck.

``raw_hours`` haelt den beim BUCHEN festgeschriebenen Wert fest. Die
Rueckrechnung ist der einzige Schreiber von ``hours``, der ihn NICHT anfasst;
jeder menschliche Schreiber zieht ihn mit (siehe den Kommentar an der Spalte in
``app/models/absence.py``). ``TimeEntry`` hat mit ``raw_start_time``/
``raw_end_time`` (#201) dieselbe Sicherung.

Nullable + Backfill: fuer Bestandsdaten ist der aktuelle ``hours``-Wert der
bestmoegliche bekannte Ursprungswert — wo bereits nachgerechnet wurde, ist der
echte Ursprung nirgends mehr abgelegt. Die Spalte bleibt nullable (kein
``NOT NULL``), weil ein spaeterer ``downgrade``/``upgrade``-Zyklus sonst am
Rohwert scheitern koennte und weil ``hours`` selbst die einzige Pflichtangabe
bleibt; der Listener fuellt jede neue Zeile.

Der Spaltentyp ist absichtlich identisch zu ``absences.hours``
(``Numeric(4, 2)``) — ein abweichender Typ wuerde beim Vergleich „Rohwert vs.
gerechneter Wert" still runden.

KEIN Index: ``raw_hours`` wird nie gefiltert oder sortiert, es wird ausschliesslich
zusammen mit seiner Zeile gelesen.
"""
from alembic import op
import sqlalchemy as sa

revision = "068_absence_raw_hours"
down_revision = "067_schedule_history"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("absences", sa.Column("raw_hours", sa.Numeric(4, 2), nullable=True))
    # Backfill. ``WHERE raw_hours IS NULL`` haelt den Lauf idempotent (die Spalte
    # ist frisch, aber ein wiederholtes Ausfuehren darf nie einen bereits
    # gesetzten Rohwert ueberschreiben — genau das waere der Datenverlust, gegen
    # den diese Spalte gebaut ist).
    op.execute("UPDATE absences SET raw_hours = hours WHERE raw_hours IS NULL")


def downgrade():
    """Verlustfrei fuer alles, was das Alt-Modell kannte: ``hours`` bleibt
    unberuehrt. Verloren geht nur der Rohwert selbst — den es vor dieser
    Migration ohnehin nicht gab."""
    op.drop_column("absences", "raw_hours")
