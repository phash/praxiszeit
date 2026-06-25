"""Add Schichtplanung (shift planning) tables — Issue #305.

Five tenant-scoped tables for the shift-planning feature (a pure planning
artefact, decoupled from the ArbZG/time-tracking model):

* ``locations``         — Standorte
* ``workstations``      — Arbeitsplätze (optional location)
* ``shift_plans``       — named weekly templates (multiple may be active)
* ``shift_slots``       — workstation × weekday × time window + min staffing
* ``shift_assignments`` — employees assigned to a slot

Each gets ``tenant_id`` (NOT NULL FK + index) and the standard
``tenant_isolation`` RLS policy (NOT-NULL-tenant variant from migration 027).
The feature is additionally gated at runtime by the ``shift_planning_enabled``
system setting (Default off) — no data migration is needed.

Revision ID: 053_add_shift_planning
Revises: 052_add_absence_half_day
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '053_add_shift_planning'
down_revision = '052_add_absence_half_day'
branch_labels = None
depends_on = None

# Order matters for FK dependencies (create parents first, drop children first).
_RLS_TABLES = ['locations', 'workstations', 'shift_plans', 'shift_slots', 'shift_assignments']


def upgrade() -> None:
    # 1. locations
    op.create_table(
        'locations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_locations_tenant_id', 'locations', ['tenant_id'])
    op.create_unique_constraint('uq_tenant_location_name', 'locations', ['tenant_id', 'name'])

    # 2. workstations
    op.create_table(
        'workstations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('location_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('locations.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('color', sa.String(7), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_workstations_tenant_id', 'workstations', ['tenant_id'])
    op.create_index('ix_workstations_location_id', 'workstations', ['location_id'])
    op.create_unique_constraint('uq_tenant_workstation_name', 'workstations', ['tenant_id', 'name'])

    # 3. shift_plans
    op.create_table(
        'shift_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_shift_plans_tenant_id', 'shift_plans', ['tenant_id'])
    op.create_unique_constraint('uq_tenant_shift_plan_name', 'shift_plans', ['tenant_id', 'name'])

    # 4. shift_slots
    op.create_table(
        'shift_slots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('shift_plan_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('shift_plans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workstation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('workstations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('weekday', sa.SmallInteger(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('min_staff', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_shift_slots_tenant_id', 'shift_slots', ['tenant_id'])
    op.create_index('ix_shift_slots_shift_plan_id', 'shift_slots', ['shift_plan_id'])
    op.create_index('ix_shift_slots_workstation_id', 'shift_slots', ['workstation_id'])
    op.create_index('ix_shift_slots_plan_weekday', 'shift_slots', ['tenant_id', 'shift_plan_id', 'weekday'])

    # 5. shift_assignments
    op.create_table(
        'shift_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('shift_slot_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('shift_slots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_shift_assignments_tenant_id', 'shift_assignments', ['tenant_id'])
    op.create_index('ix_shift_assignments_shift_slot_id', 'shift_assignments', ['shift_slot_id'])
    op.create_index('ix_shift_assignments_user_id', 'shift_assignments', ['user_id'])
    op.create_unique_constraint('uq_tenant_slot_user', 'shift_assignments',
                                ['tenant_id', 'shift_slot_id', 'user_id'])

    # 6. RLS — enable + force + tenant_isolation policy (NOT-NULL tenant_id variant)
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
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
    for table in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table('shift_assignments')
    op.drop_table('shift_slots')
    op.drop_table('shift_plans')
    op.drop_table('workstations')
    op.drop_table('locations')
