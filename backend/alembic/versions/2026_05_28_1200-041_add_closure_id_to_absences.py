"""Add absences.closure_id FK to company_closures + backfill from note string.

Betriebsferien-Absences wurden bisher nur über den Note-String
('Betriebsferien: <name>') mit ihrer CompanyClosure verknüpft. Das ist
fragil: nach einer Umbenennung oder manuellem Editieren der Notiz greift das
Matching nicht mehr. Diese Migration ersetzt die String-Verknüpfung durch
einen sauberen Fremdschlüssel `absences.closure_id`.

`ON DELETE SET NULL`: wird ein Closure gelöscht, sollen die zugehörigen
Absences nicht automatisch per Kaskade verschwinden — der Router löscht sie
explizit (mit tenant_id-Filter). Bleibt ein Datensatz verwaist, wird die
Referenz lediglich genullt statt einen FK-Constraint-Fehler zu werfen.

Backfill: bestehende VACATION-Absences mit note LIKE 'Betriebsferien: %'
werden dem passenden CompanyClosure zugeordnet — gleicher tenant_id,
Note-Suffix == closure.name, und das Absence-Datum liegt im Closure-Zeitraum.

Revision ID: 041_absence_closure_id
Revises: 040_custom_holiday_fields
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = '041_absence_closure_id'
down_revision = '040_custom_holiday_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'absences',
        sa.Column('closure_id', PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_absences_closure_id',
        'absences',
        'company_closures',
        ['closure_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_absences_closure_id', 'absences', ['closure_id'])

    # Backfill: link existing Betriebsferien-Absences to their CompanyClosure
    # via the legacy note string. Match on tenant + name suffix + date range.
    # 'Betriebsferien: ' is 16 chars -> substring from position 17 (1-based).
    op.execute(
        """
        UPDATE absences a
        SET closure_id = c.id
        FROM company_closures c
        WHERE a.closure_id IS NULL
          AND a.type = 'VACATION'
          AND a.note LIKE 'Betriebsferien: %'
          AND a.tenant_id = c.tenant_id
          AND substring(a.note FROM 17) = c.name
          AND a.date >= c.start_date
          AND a.date <= c.end_date
        """
    )


def downgrade() -> None:
    op.drop_index('ix_absences_closure_id', table_name='absences')
    op.drop_constraint('fk_absences_closure_id', 'absences', type_='foreignkey')
    op.drop_column('absences', 'closure_id')
