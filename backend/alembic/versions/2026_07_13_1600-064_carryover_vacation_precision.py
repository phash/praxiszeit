"""#383: year_carryovers.vacation_days Numeric(4,1) → Numeric(5,2)

Kundenreport (philvdb): der Urlaubs-Übertrag braucht 2 Nachkommastellen (krumme
Werte, z. B. 3,33 Tage). Die alte Numeric(4,1) rundete auf 1 Stelle. Additiv/
verlustfrei im Up (mehr Präzision); Down rundet zurück auf 1 Stelle (lossy —
Natur einer Präzisionsreduktion, akzeptiert).
"""
from alembic import op
import sqlalchemy as sa

revision = "064_carryover_vac_prec"
down_revision = "063_agreed_monthly_hours"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "year_carryovers", "vacation_days",
        type_=sa.Numeric(5, 2),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "year_carryovers", "vacation_days",
        type_=sa.Numeric(4, 1),
        existing_nullable=False,
    )
