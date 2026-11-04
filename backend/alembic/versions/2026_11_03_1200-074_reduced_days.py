"""Add reduced_days (Teil B, Verkuerzte Tage).

Ein verkuerzter Tag begrenzt das Tagessoll auf hoechstens ``max_hours`` Stunden
(Soll = min(Tagessoll laut Snapshot, max_hours)). Die Migration legt nur die
Tabelle an und aendert kein Altergebnis.

``created_by`` ist ``ON DELETE SET NULL``: die Zeile gehoert dem Mandanten, nicht
dem Ersteller, und darf den Art.-17-Hard-Delete (``admin_users.purge_user``)
nicht blockieren.

Revision ID: 074_reduced_days
Revises: 073_work_blocks
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "074_reduced_days"
down_revision = "073_work_blocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reduced_days",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("max_hours", sa.Numeric(4, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("tenant_id", "date", name="uq_reduced_days_tenant_date"),
    )
    # Kein eigener Index auf tenant_id: das UNIQUE (tenant_id, date) liefert ihn.

    op.execute("ALTER TABLE reduced_days ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE reduced_days FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON reduced_days
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
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON reduced_days")
    op.drop_table("reduced_days")
