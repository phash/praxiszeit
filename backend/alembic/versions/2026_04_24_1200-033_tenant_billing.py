"""Tenant billing fields + tenant_invoices table (SaaS Phase 2 / Issue #93)

Adds SaaS-specific billing columns to ``tenants`` and creates a cached
``tenant_invoices`` table that mirrors Stripe invoices (sync'd via webhook
in Phase 4). Existing tenants are backfilled with ``plan='enterprise'`` so
on-prem installs aren't treated as unpaid trials.

Revision ID: 033_tenant_billing
Revises: 032_totp_replay
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '033_tenant_billing'
down_revision = '032_totp_replay'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extend tenants table
    # NB: nullable columns / server_defaults so existing rows are filled in
    # without a separate UPDATE pass. Pydantic enums validate the allowed
    # values at the app layer; we keep the DB column as free-form varchar
    # so plan expansion (e.g. new 'education' tier) doesn't need a migration.
    op.add_column('tenants', sa.Column(
        'plan', sa.String(20), nullable=False, server_default='trial'
    ))
    op.add_column('tenants', sa.Column(
        'subscription_status', sa.String(20), nullable=False, server_default='active'
    ))
    op.add_column('tenants', sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tenants', sa.Column('seat_limit', sa.Integer(), nullable=True))
    op.add_column('tenants', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('stripe_subscription_id', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('billing_email', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('company_name', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('vat_id', sa.String(50), nullable=True))
    op.add_column('tenants', sa.Column('country', sa.String(2), nullable=True))
    op.add_column('tenants', sa.Column('billing_address', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_unique_constraint('uq_tenants_stripe_customer_id', 'tenants', ['stripe_customer_id'])
    op.create_unique_constraint('uq_tenants_stripe_subscription_id', 'tenants', ['stripe_subscription_id'])

    # 2. Backfill existing tenants — on-prem default tenant should never
    #    be billed. 'enterprise' + no seat_limit = unlimited, no Stripe.
    op.execute("""
        UPDATE tenants
        SET plan = 'enterprise',
            subscription_status = 'active'
        WHERE mode = 'single' OR slug = 'default'
    """)

    # 3. tenant_invoices cache table (populated by Stripe webhook in Phase 4)
    op.create_table(
        'tenant_invoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stripe_invoice_id', sa.String(255), nullable=False, unique=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='eur'),
        # open | paid | uncollectible | void | draft — mirrors Stripe
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hosted_invoice_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_tenant_invoices_tenant_id'),
    )
    op.create_index('ix_tenant_invoices_tenant_id', 'tenant_invoices', ['tenant_id'])
    op.create_index('ix_tenant_invoices_created_at', 'tenant_invoices', ['created_at'])

    # 4. Enable RLS on tenant_invoices (same pattern as migration 027)
    op.execute("ALTER TABLE tenant_invoices ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_invoices FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON tenant_invoices
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
    # Drop tenant_invoices
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_invoices")
    op.execute("ALTER TABLE tenant_invoices DISABLE ROW LEVEL SECURITY")
    op.drop_index('ix_tenant_invoices_created_at', 'tenant_invoices')
    op.drop_index('ix_tenant_invoices_tenant_id', 'tenant_invoices')
    op.drop_table('tenant_invoices')

    # Drop billing columns from tenants
    op.drop_constraint('uq_tenants_stripe_subscription_id', 'tenants', type_='unique')
    op.drop_constraint('uq_tenants_stripe_customer_id', 'tenants', type_='unique')
    op.drop_column('tenants', 'billing_address')
    op.drop_column('tenants', 'country')
    op.drop_column('tenants', 'vat_id')
    op.drop_column('tenants', 'company_name')
    op.drop_column('tenants', 'billing_email')
    op.drop_column('tenants', 'stripe_subscription_id')
    op.drop_column('tenants', 'stripe_customer_id')
    op.drop_column('tenants', 'seat_limit')
    op.drop_column('tenants', 'trial_ends_at')
    op.drop_column('tenants', 'subscription_status')
    op.drop_column('tenants', 'plan')
