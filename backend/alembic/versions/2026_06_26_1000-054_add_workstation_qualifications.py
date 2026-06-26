"""Add workstation_qualifications (Einweisungs-/Skill-Matrix, #305 M2d).

Per-employee qualification for a workstation (which workstations a person is
trained for). Pure planning metadata, tenant-scoped with the standard
``tenant_isolation`` RLS policy. Additive — no backfill.

Revision ID: 054_add_workstation_quals
Revises: 053_add_shift_planning
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '054_add_workstation_quals'
down_revision = '053_add_shift_planning'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'workstation_qualifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workstation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('workstations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_workstation_qualifications_tenant_id', 'workstation_qualifications', ['tenant_id'])
    op.create_index('ix_workstation_qualifications_user_id', 'workstation_qualifications', ['user_id'])
    op.create_index('ix_workstation_qualifications_workstation_id', 'workstation_qualifications', ['workstation_id'])
    op.create_unique_constraint('uq_tenant_user_workstation', 'workstation_qualifications',
                                ['tenant_id', 'user_id', 'workstation_id'])

    op.execute("ALTER TABLE workstation_qualifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workstation_qualifications FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON workstation_qualifications
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON workstation_qualifications")
    op.drop_table('workstation_qualifications')
