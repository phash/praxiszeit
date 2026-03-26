"""Fix review findings: system_settings composite PK, tenants RLS policy

Revision ID: 028_fix_review_findings
Revises: 027_add_multi_tenant
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa

revision = '028_fix_review_findings'
down_revision = '027_add_multi_tenant'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Fix system_settings: composite PK (key, tenant_id) --
    op.execute(
        "UPDATE system_settings SET tenant_id = '00000000-0000-0000-0000-000000000001' "
        "WHERE tenant_id IS NULL"
    )
    op.alter_column('system_settings', 'tenant_id', nullable=False)
    op.drop_constraint('system_settings_pkey', 'system_settings', type_='primary')
    op.create_primary_key('system_settings_pkey', 'system_settings', ['key', 'tenant_id'])

    # Update system_settings RLS policy: remove OR tenant_id IS NULL (no longer possible)
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON system_settings")
    op.execute("""
        CREATE POLICY tenant_isolation ON system_settings
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)

    # -- Fix tenants: add RLS policy --
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON tenants
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenants")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")

    # Restore system_settings nullable RLS policy
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON system_settings")
    op.execute("""
        CREATE POLICY tenant_isolation ON system_settings
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR tenant_id IS NULL
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR tenant_id IS NULL
        )
    """)

    op.drop_constraint('system_settings_pkey', 'system_settings', type_='primary')
    op.create_primary_key('system_settings_pkey', 'system_settings', ['key'])
    op.alter_column('system_settings', 'tenant_id', nullable=True)
