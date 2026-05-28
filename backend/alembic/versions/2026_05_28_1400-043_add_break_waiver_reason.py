"""Add break_waiver_reason to time_entries + change_requests (Pflicht-Pause-Ausnahme).

#144: Nicht von §18 ArbZG befreite Mitarbeiter können ausnahmsweise einen
Eintrag ohne die gesetzlich geforderte Pause erfassen, wenn die Pause
nachweislich nicht möglich war — mit einer Pflicht-Begründung. Diese
Begründung wird am Zeiteintrag (`time_entries.break_waiver_reason`)
persistiert, damit die Abweichung im Reporting/Audit nachvollziehbar bleibt.

Ist die Ausnahme genehmigungspflichtig (`break_exception_requires_approval`),
wird statt des Eintrags ein ChangeRequest (request_type=CREATE) angelegt; der
trägt die Begründung in `change_requests.break_waiver_reason`, sodass bei der
Genehmigung der materialisierte Eintrag sein `break_waiver_reason` gesetzt
bekommt. Beide Spalten sind nullable — Bestandsdaten brauchen keinen Backfill.

Außerdem wird der Setting-Default `break_exception_requires_approval` = 'false'
für den Default-Tenant gesetzt (das Setting ist pro Praxis konfigurierbar).

Revision ID: 043_break_waiver
Revises: 042_paid_leave_closure_flag
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa


revision = '043_break_waiver'
down_revision = '042_paid_leave_closure_flag'
branch_labels = None
depends_on = None


# Default-Tenant UUID (single-tenant On-Prem-Bootstrap, vgl. CLAUDE.md).
_DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    op.add_column(
        'time_entries',
        sa.Column('break_waiver_reason', sa.Text(), nullable=True),
    )
    op.add_column(
        'change_requests',
        sa.Column('break_waiver_reason', sa.Text(), nullable=True),
    )

    # Setting-Default für den vorhandenen Default-Tenant. Neue Tenants (SaaS)
    # bekommen den Default zur Laufzeit über das get_setting-Default-Argument;
    # ein expliziter Eintrag ist nur für den On-Prem-Default-Tenant nötig,
    # damit die Admin-Settings-Liste den Toggle direkt anzeigt.
    op.execute(
        "INSERT INTO system_settings (key, tenant_id, value, description) "
        f"VALUES ('break_exception_requires_approval', '{_DEFAULT_TENANT_ID}', 'false', "
        "'Pflicht-Pause-Ausnahmen erfordern Admin-Genehmigung') "
        "ON CONFLICT (key, tenant_id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key = 'break_exception_requires_approval'"
    )
    op.drop_column('change_requests', 'break_waiver_reason')
    op.drop_column('time_entries', 'break_waiver_reason')
