"""Track who last modified a vacation request.

Adds ``last_modified_by`` + ``last_modified_at`` to ``vacation_requests``.
The motivation is DSGVO-style transparency: when an admin edits a
pending request that was originally filed by an employee, the employee
should be able to see *that* it was modified and *by whom*, not just
the after-state. The columns also make the audit-log query a single
JOIN instead of a fragile LIKE-on-format-string.

``last_modified_by`` is set by ``apply_vacation_request_patch`` on
every non-noop edit. NULL means the request has not been modified
since creation. The admin's ``review`` (approve/reject) writes
``reviewed_by``, not these columns — they specifically track CONTENT
changes.

Revision ID: 038_vr_last_modified
Revises: 037_widen_audit_source
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa


revision = '038_vr_last_modified'
down_revision = '037_widen_audit_source'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'vacation_requests',
        sa.Column(
            'last_modified_by',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.add_column(
        'vacation_requests',
        sa.Column(
            'last_modified_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('vacation_requests', 'last_modified_at')
    op.drop_column('vacation_requests', 'last_modified_by')
