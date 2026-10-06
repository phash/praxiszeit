"""#485: §10-Ausnahmegrund im Aenderungsantrag

``change_requests.proposed_sunday_exception_reason``
    Seit #479 lassen sich im Monatsjournal Eintraege an Sonn- und Feiertagen
    beantragen. Der Antrag kannte aber kein Feld fuer den Ausnahmegrund nach
    §10 ArbZG — der Eintrag, der bei der Genehmigung entsteht, hatte deshalb
    nie einen. Die Spalte nimmt den Grund auf; die Genehmigung uebertraegt ihn
    auf ``time_entries.sunday_exception_reason``.

    ``Text`` wie ``break_waiver_reason``: die Laengengrenze sitzt am Rand
    (Pydantic ``max_length=2000``), nicht in der Datenbank. Nullable, kein
    Default — bestehende Antraege haben keinen Grund und brauchen keinen.

``change_requests`` ist bereits mandantenbezogen mit RLS-Policy — reine
Spalten-Ergaenzung, keine Policy-Aenderung noetig.
"""
from alembic import op
import sqlalchemy as sa


revision = "072_cr_sunday_reason"
down_revision = "071_security_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "change_requests",
        sa.Column("proposed_sunday_exception_reason", sa.Text(), nullable=True),
    )


def downgrade():
    """Verloren geht nur der Grund in noch offenen oder abgeschlossenen
    Antraegen; der genehmigte Wert steht am Zeiteintrag und bleibt."""
    op.drop_column("change_requests", "proposed_sunday_exception_reason")
