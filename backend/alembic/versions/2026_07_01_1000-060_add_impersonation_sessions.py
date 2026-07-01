"""Add impersonation_sessions (read-only "Login als …", #370).

Logs each read-only impersonation session (admin views the app as an employee)
for DSGVO Art. 5(2) accountability. Tenant-scoped with the standard
``tenant_isolation`` RLS policy. Both user FKs ON DELETE CASCADE so the Art. 17
purge of a user cannot FK-violate.

Revision ID: 060_impersonation_sessions
Revises: 059_cr_absence_ondelete
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '060_impersonation_sessions'
down_revision = '059_cr_absence_ondelete'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'impersonation_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('impersonator_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_impersonation_sessions_tenant_id', 'impersonation_sessions', ['tenant_id'])
    op.create_index('ix_impersonation_sessions_impersonator_id', 'impersonation_sessions', ['impersonator_id'])
    op.create_index('ix_impersonation_sessions_target_id', 'impersonation_sessions', ['target_id'])
    op.create_index('ix_impersonation_sessions_tenant_started', 'impersonation_sessions', ['tenant_id', 'started_at'])

    op.execute("ALTER TABLE impersonation_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE impersonation_sessions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON impersonation_sessions
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
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON impersonation_sessions")
    op.drop_index('ix_impersonation_sessions_tenant_started', table_name='impersonation_sessions')
    op.drop_index('ix_impersonation_sessions_target_id', table_name='impersonation_sessions')
    op.drop_index('ix_impersonation_sessions_impersonator_id', table_name='impersonation_sessions')
    op.drop_index('ix_impersonation_sessions_tenant_id', table_name='impersonation_sessions')
    op.drop_table('impersonation_sessions')
