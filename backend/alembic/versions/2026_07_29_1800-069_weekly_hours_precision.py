"""#431: users.weekly_hours Numeric(4,1) → Numeric(4,2)

``working_hours_changes.weekly_hours`` traegt seit 067 zwei Nachkommastellen —
genau deswegen, weil die Summe eines Tagesplans krumm sein kann (Mo 4,25 + Di
4,5 + Mi 4,5 + Do 4,5 = 17,75). Die User-Zeile blieb auf ``Numeric(4,1)``.

``_sync_user_from_change`` (admin_users.py) spiegelt nach jedem Anlegen/Loeschen
einer Historien-Zeile den vollstaendigen Snapshot auf die User-Zeile zurueck.
Postgres rundet dabei still beim Schreiben: aus 17,75 wurde 17,8. Danach
widersprachen sich Benutzerliste/Art.-15-Export (17,8) und
Historie/Berichte/Soll-Berechnung (17,75) — der Resync unterlief also genau die
Verbreiterung, fuer die 067 angetreten war.

Erreichbar ueber die API: die Tagesfelder sind laut Schema ``ge=0, le=24`` und
``check_mode`` rundet die Summe auf zwei Stellen; nur die Dialog-Eingabefelder
im Frontend stehen auf ``step="0.5"``.

SQLite ignoriert die Numeric-Precision vollstaendig → die Unit-Suite kann diese
Fehlerklasse nicht sehen (wie #383/#408). Der Round-Trip ist gegen ein echtes
Postgres verifiziert.

Up ist verlustfrei (Praezision wird nur erweitert). Down rundet auf eine
Nachkommastelle zurueck — lossy, das ist die Natur einer Praezisionsreduktion
und identisch zur Entscheidung in 064/066.
"""
from alembic import op
import sqlalchemy as sa

revision = "069_weekly_hours_precision"
down_revision = "068_absence_raw_hours"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "users", "weekly_hours",
        existing_type=sa.Numeric(4, 1),
        type_=sa.Numeric(4, 2),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "users", "weekly_hours",
        existing_type=sa.Numeric(4, 2),
        type_=sa.Numeric(4, 1),
        existing_nullable=False,
        postgresql_using="round(weekly_hours, 1)",
    )
