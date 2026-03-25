"""Add multi-tenant support: tenants table, tenant_id on all tables, updated constraints

Revision ID: 027_add_multi_tenant
Revises: 026_add_year_carryovers
Create Date: 2026-03-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '027_add_multi_tenant'
down_revision = '026_add_year_carryovers'
branch_labels = None
depends_on = None

_NOT_NULL_TABLES = [
    'time_entries',
    'absences',
    'vacation_requests',
    'change_requests',
    'time_entry_audit_logs',
    'working_hours_changes',
    'year_carryovers',
    'public_holidays',
    'company_closures',
    'error_logs',
]

_NULLABLE_TABLES = [
    'users',
    'system_settings',
]


def upgrade() -> None:
    # 1. Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), unique=True, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('mode', sa.String(20), nullable=False, server_default='multi'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # 2. Insert default tenant
    op.execute(
        "INSERT INTO tenants (id, name, slug, is_active, mode) "
        "VALUES ('00000000-0000-0000-0000-000000000001', 'Default', 'default', true, 'single')"
    )

    # 3. Add tenant_id to NOT NULL tables
    for table in _NOT_NULL_TABLES:
        op.add_column(table, sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.execute(f"UPDATE {table} SET tenant_id = '00000000-0000-0000-0000-000000000001'")
        op.alter_column(table, 'tenant_id', nullable=False)
        op.create_foreign_key(f'fk_{table}_tenant_id', table, 'tenants', ['tenant_id'], ['id'])
        op.create_index(f'ix_{table}_tenant_id', table, ['tenant_id'])

    # 4. Add tenant_id to nullable tables
    for table in _NULLABLE_TABLES:
        op.add_column(table, sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.execute(f"UPDATE {table} SET tenant_id = '00000000-0000-0000-0000-000000000001'")
        op.create_foreign_key(f'fk_{table}_tenant_id', table, 'tenants', ['tenant_id'], ['id'])
        op.create_index(f'ix_{table}_tenant_id', table, ['tenant_id'])

    # 5. Drop old unique constraints and create new tenant-scoped ones
    op.drop_constraint('users_username_key', 'users', type_='unique')
    op.create_unique_constraint('uq_tenant_username', 'users', ['tenant_id', 'username'])

    op.drop_constraint('uq_user_date_start', 'time_entries', type_='unique')
    op.create_unique_constraint('uq_tenant_user_date_start', 'time_entries',
                                ['tenant_id', 'user_id', 'date', 'start_time'])

    op.drop_constraint('uq_user_date_type', 'absences', type_='unique')
    op.create_unique_constraint('uq_tenant_user_date_type', 'absences',
                                ['tenant_id', 'user_id', 'date', 'type'])

    op.drop_constraint('public_holidays_date_key', 'public_holidays', type_='unique')
    op.create_unique_constraint('uq_tenant_holiday_date', 'public_holidays',
                                ['tenant_id', 'date'])

    op.drop_constraint('uq_year_carryover_user_year', 'year_carryovers', type_='unique')
    op.create_unique_constraint('uq_tenant_year_carryover_user_year', 'year_carryovers',
                                ['tenant_id', 'user_id', 'year'])

    # 6. Enable RLS on all tables with tenant_id
    all_tables = _NOT_NULL_TABLES + ['users', 'system_settings']
    for table in all_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # 7. Create RLS policies — standard tables (NOT NULL tenant_id)
    for table in _NOT_NULL_TABLES:
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                current_setting('app.tenant_id', true) IS NULL
                OR tenant_id = current_setting('app.tenant_id')::uuid
            )
            WITH CHECK (
                current_setting('app.tenant_id', true) IS NULL
                OR tenant_id = current_setting('app.tenant_id')::uuid
            )
        """)

    # 8. Create RLS policies — nullable tenant_id tables (users, system_settings)
    for table in ['users', 'system_settings']:
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                current_setting('app.tenant_id', true) IS NULL
                OR tenant_id = current_setting('app.tenant_id')::uuid
                OR tenant_id IS NULL
            )
            WITH CHECK (
                current_setting('app.tenant_id', true) IS NULL
                OR tenant_id = current_setting('app.tenant_id')::uuid
                OR tenant_id IS NULL
            )
        """)


def downgrade() -> None:
    # Remove RLS policies and disable RLS
    all_tables = _NOT_NULL_TABLES + ['users', 'system_settings']
    for table in all_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Reverse unique constraints
    op.drop_constraint('uq_tenant_year_carryover_user_year', 'year_carryovers', type_='unique')
    op.create_unique_constraint('uq_year_carryover_user_year', 'year_carryovers',
                                ['user_id', 'year'])

    op.drop_constraint('uq_tenant_holiday_date', 'public_holidays', type_='unique')
    op.create_unique_constraint('public_holidays_date_key', 'public_holidays', ['date'])

    op.drop_constraint('uq_tenant_user_date_type', 'absences', type_='unique')
    op.create_unique_constraint('uq_user_date_type', 'absences',
                                ['user_id', 'date', 'type'])

    op.drop_constraint('uq_tenant_user_date_start', 'time_entries', type_='unique')
    op.create_unique_constraint('uq_user_date_start', 'time_entries',
                                ['user_id', 'date', 'start_time'])

    op.drop_constraint('uq_tenant_username', 'users', type_='unique')
    op.create_unique_constraint('users_username_key', 'users', ['username'])

    # Drop tenant_id from all tables
    all_tables = _NULLABLE_TABLES + _NOT_NULL_TABLES
    for table in all_tables:
        op.drop_index(f'ix_{table}_tenant_id', table)
        op.drop_constraint(f'fk_{table}_tenant_id', table, type_='foreignkey')
        op.drop_column(table, 'tenant_id')

    # Drop tenants table
    op.drop_table('tenants')
