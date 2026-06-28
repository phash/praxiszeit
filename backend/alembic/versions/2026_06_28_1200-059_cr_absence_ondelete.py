"""Fix #1: change_requests.absence_id FK → ON DELETE SET NULL.

Without an ondelete rule, deleting an absence that is referenced by a
ChangeRequest fails with a ForeignKeyViolation (500) on Postgres — this breaks
absence-delete/-change CR approval, direct delete_absence, the SICK vacation
refund and the DSGVO purge. SET NULL mirrors change_requests.time_entry_id.

Revision ID: 059_cr_absence_ondelete
Revises: 058_carryover_source
Create Date: 2026-06-28
"""
from alembic import op


revision = '059_cr_absence_ondelete'
down_revision = '058_carryover_source'
branch_labels = None
depends_on = None

_FK = 'fk_change_requests_absence_id'


def upgrade() -> None:
    op.drop_constraint(_FK, 'change_requests', type_='foreignkey')
    op.create_foreign_key(
        _FK, 'change_requests', 'absences',
        ['absence_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(_FK, 'change_requests', type_='foreignkey')
    op.create_foreign_key(
        _FK, 'change_requests', 'absences',
        ['absence_id'], ['id'],
    )
