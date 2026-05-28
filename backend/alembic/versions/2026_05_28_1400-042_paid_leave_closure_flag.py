"""Add PAID_LEAVE absence type + company_closures.counts_as_vacation (#145).

Betriebsferien (company closures) can now be booked either as Urlaub
(VACATION, deducts the vacation budget — legacy behaviour) or as bezahlte
Freistellung (PAID_LEAVE, paid leave like a public holiday: reduces the
target to 0, no vacation-budget deduction, balance-neutral).

Two changes ship together:

1. New enum value ``PAID_LEAVE`` on the Postgres ``absencetype`` enum.
   IMPORTANT: SQLAlchemy ``Enum(AbsenceType)`` stores the member NAME
   (uppercase) in Postgres — existing values are 'VACATION', 'SICK',
   'TRAINING', 'OVERTIME', 'OTHER'. The new value must therefore be the
   uppercase name ``'PAID_LEAVE'`` (NOT the lowercase ``"paid_leave"``
   value), mirroring migration 023 which added ``'OVERTIME'``.

   ``ALTER TYPE ... ADD VALUE`` is Postgres-only. The SQLite test suite
   builds the schema from the model via ``create_all`` and therefore picks
   up the new enum member automatically — no SQLite-specific step needed.
   PG16 permits ADD VALUE inside a transaction block as long as the value
   is not USED in the same migration (we don't use it here). The
   ``IF NOT EXISTS`` guard makes the statement idempotent.

2. New column ``company_closures.counts_as_vacation BOOLEAN NOT NULL
   DEFAULT true``. The default backfills existing closures as VACATION,
   preserving the previous behaviour.

Downgrade: the column is dropped; the enum value is left in place because
Postgres cannot easily remove an enum value (same as migration 023).

Revision ID: 042_paid_leave_closure_flag
Revises: 041_absence_closure_id
Create Date: 2026-05-28 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '042_paid_leave_closure_flag'
down_revision = '041_absence_closure_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. New enum value. Uppercase NAME — SQLAlchemy stores the member name,
    #    not the lowercase value (see migration 001 which created the type
    #    with 'VACATION'/'SICK'/... and migration 023 which added 'OVERTIME').
    #    IF NOT EXISTS keeps it idempotent across re-runs.
    op.execute("ALTER TYPE absencetype ADD VALUE IF NOT EXISTS 'PAID_LEAVE'")

    # 2. Closure flag — defaults to true so existing closures keep producing
    #    VACATION absences (legacy behaviour).
    op.add_column(
        'company_closures',
        sa.Column(
            'counts_as_vacation',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column('company_closures', 'counts_as_vacation')
    # PostgreSQL doesn't support removing enum values — leave 'PAID_LEAVE' in
    # place. It is harmless if unused.
