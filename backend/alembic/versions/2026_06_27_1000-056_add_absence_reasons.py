"""Add absence_reasons + absences.reason_id (eigene Abwesenheitsgründe, #312).

Tenant-defined custom absence reasons (name + colour + base_behavior). An
absence may reference one via reason_id (label/colour overlay); the absence's
``type`` still drives the calculation. Additive — no backfill.

Revision ID: 056_add_absence_reasons
Revises: 055_add_shift_plan_schedule
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '056_add_absence_reasons'
down_revision = '055_add_shift_plan_schedule'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'absence_reasons',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('base_behavior', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_absence_reasons_tenant_id', 'absence_reasons', ['tenant_id'])
    op.create_unique_constraint('uq_absence_reason_tenant_name', 'absence_reasons', ['tenant_id', 'name'])

    op.execute("ALTER TABLE absence_reasons ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE absence_reasons FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON absence_reasons
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)

    op.add_column('absences', sa.Column('reason_id', postgresql.UUID(as_uuid=True),
                                        sa.ForeignKey('absence_reasons.id', ondelete='SET NULL'),
                                        nullable=True))
    op.create_index('ix_absences_reason_id', 'absences', ['reason_id'])


def downgrade() -> None:
    op.drop_index('ix_absences_reason_id', table_name='absences')
    op.drop_column('absences', 'reason_id')
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON absence_reasons")
    op.drop_table('absence_reasons')
