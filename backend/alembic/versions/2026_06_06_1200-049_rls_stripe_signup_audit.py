"""Add RLS to stripe_events + signup_audit_log (defense-in-depth / invariant).

Both tables carry a ``tenant_id`` but were created without Row-Level-Security
(035 stripe_events / 034 signup_audit_log). Every access path runs in
SUPERADMIN context — the Stripe webhook via ``_webhook_db`` (billing.py), the
public signup via ``_public_db`` (public_signup.py), the lifecycle
anonymization via the scheduler, and reads via ``/api/superadmin``. Enabling
FORCE RLS with the standard ``tenant_isolation`` policy is therefore a no-op
for the current access pattern, but it restores the project invariant ("every
tenant_id table has an RLS policy") and closes the latent cross-tenant leak
the moment a future tenant-scoped code path ever touches these tables
(e.g. a billing-history feature reading ``stripe_events``).

The 034 note "No RLS on signup_audit_log: rows are written by anonymous
requesters" is superseded: the HTTP requester is anonymous, but the DB session
IS superadmin (``_public_db`` calls ``set_superadmin_context``), so the policy
applies cleanly to the existing writes (which set ``tenant_id`` to the new
tenant, e.g. signup_service.py:160/201/245).

NOTE: RLS is not exercised on the SQLite unit-test engine — verify against
Postgres (test_tenant_rls.py / test_cross_tenant_api.py) before deploying.

Revision ID: 049_rls_stripe_signup_audit
Revises: 048_add_work_window
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '049_rls_stripe_signup_audit'
down_revision = '048_add_work_window'
branch_labels = None
depends_on = None

# Tables that carry tenant_id but were created without an RLS policy.
_TABLES = ('stripe_events', 'signup_audit_log')


def upgrade() -> None:
    for tbl in _TABLES:
        # ENABLE + FORCE so even the table owner is subject to the policy
        # (matches migration 027 / 034). NULL-tenant rows (pre-tenant signup
        # attempts, unmapped webhook events) remain visible to superadmin only.
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {tbl}
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
    for tbl in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
