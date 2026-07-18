"""#408: users.vacation_days Integer → Numeric(4,1)

Kundenreport (philvdb): der Jahresurlaubsanspruch braucht eine Nachkommastelle
(z. B. 28×3/5 = 16,8 Tage für eine 3-Tage-Teilzeitkraft). Bisher nur ganzzahlig
→ Rundung auf 17 erzeugte 0,2 Tage Ungerechtigkeit vs. anderen Teilzeitkräften.
Additiv/verlustfrei im Up (Integer → Numeric); Down rundet zurück auf ganze
Tage (lossy — Natur einer Präzisionsreduktion, akzeptiert).

Der Calc rechnete bereits mit `Decimal(str(user.vacation_days))`; nur Speicher/
Schema/Eingabe blockierten die Nachkommastelle.
"""
from alembic import op
import sqlalchemy as sa

revision = "066_vacation_days_decimal"
down_revision = "065_fixed_monthly_target"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "users", "vacation_days",
        existing_type=sa.Integer(),
        type_=sa.Numeric(4, 1),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "users", "vacation_days",
        existing_type=sa.Numeric(4, 1),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="round(vacation_days)::integer",
    )
