"""Self-service signup — verification tokens + DSGVO consent audit (Phase 3 / #94)

The public ``/api/public/signup`` endpoint creates a tenant + admin user
in an inactive state and mails a verification link. The ``signup_tokens``
table stores the short-lived (24 h) verification token. ``signup_audit_log``
records the AGB + Datenschutz double-opt-in (IP + UA + timestamp) per
DSGVO Art. 7 — it's a standalone table (not extending ``time_entry_audit_log``)
because those rows need to survive tenant deletion for legal-proof purposes.

Revision ID: 034_signup_tokens
Revises: 033_tenant_billing
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '034_signup_tokens'
down_revision = '033_tenant_billing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # signup_tokens: one row per outstanding verification link.
    # token is the opaque random value emailed to the user (we store a hash,
    # not the raw token, so a DB leak doesn't grant verification privileges).
    op.create_table(
        'signup_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(128), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_signup_tokens_tenant_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_signup_tokens_user_id'),
    )
    op.create_index('ix_signup_tokens_tenant_id', 'signup_tokens', ['tenant_id'])
    op.create_index('ix_signup_tokens_user_id', 'signup_tokens', ['user_id'])
    op.create_index('ix_signup_tokens_expires_at', 'signup_tokens', ['expires_at'])

    # RLS: signup_tokens is scoped by tenant_id like everything else,
    # but the public verification endpoint looks up by token_hash with
    # superadmin context (the requester is unauthenticated).
    op.execute("ALTER TABLE signup_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE signup_tokens FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON signup_tokens
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)

    # signup_audit_log: DSGVO Art. 7 double-opt-in proof. Retained across
    # tenant deletion (see Phase 6 anonymization) so we can prove consent
    # in a dispute years later — tenant_id nullable to survive delete.
    op.create_table(
        'signup_audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('event', sa.String(30), nullable=False),
        # 'signup_requested' | 'email_verified' | 'resend_requested'
        sa.Column('ip_address', sa.String(45), nullable=True),  # IPv6 max
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('accepted_terms', sa.Boolean(), nullable=True),
        sa.Column('accepted_privacy', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_signup_audit_log_email', 'signup_audit_log', ['email'])
    op.create_index('ix_signup_audit_log_tenant_id', 'signup_audit_log', ['tenant_id'])
    op.create_index('ix_signup_audit_log_created_at', 'signup_audit_log', ['created_at'])
    # No RLS on signup_audit_log: rows are written by anonymous requesters
    # before any tenant context exists; reads are superadmin-only (/api/superadmin).


def downgrade() -> None:
    op.drop_index('ix_signup_audit_log_created_at', 'signup_audit_log')
    op.drop_index('ix_signup_audit_log_tenant_id', 'signup_audit_log')
    op.drop_index('ix_signup_audit_log_email', 'signup_audit_log')
    op.drop_table('signup_audit_log')

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON signup_tokens")
    op.execute("ALTER TABLE signup_tokens DISABLE ROW LEVEL SECURITY")
    op.drop_index('ix_signup_tokens_expires_at', 'signup_tokens')
    op.drop_index('ix_signup_tokens_user_id', 'signup_tokens')
    op.drop_index('ix_signup_tokens_tenant_id', 'signup_tokens')
    op.drop_table('signup_tokens')
