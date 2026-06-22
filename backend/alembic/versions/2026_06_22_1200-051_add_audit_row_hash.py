"""Add time_entry_audit_logs.row_hash for tamper-evidence (#121).

Per-row HMAC over the audit row content, keyed by a SECRET_KEY-derived value
(see app/core/audit_integrity.py). Nullable: pre-existing rows have no hash and
are reported as 'legacy' (not 'tampered') by /api/admin/audit/verify-integrity.

No key-dependent data backfill — it would silently no-op if SECRET_KEY were
absent at migrate time (same reasoning as migration 050). New rows get a hash
automatically via the SQLAlchemy before_insert event on the model.

Revision ID: 051_add_audit_row_hash
Revises: 050_widen_totp_secret
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '051_add_audit_row_hash'
down_revision = '050_widen_totp_secret'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'time_entry_audit_logs',
        sa.Column('row_hash', sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('time_entry_audit_logs', 'row_hash')
