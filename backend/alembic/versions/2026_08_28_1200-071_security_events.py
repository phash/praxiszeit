"""Add security_events (#425).

Bis hierher gab es im Projekt keine Ablage fuer sicherheitsrelevante Ereignisse:
``time_entry_audit_logs`` ist §16-Domaene und ueber ``row_hash`` (#121)
manipulationsgeschuetzt — eine Zweckentfremdung verschmutzt den Beleg —, und das
rotierende ``logs/praxiszeit.log`` traegt keinen Nachweis nach Art. 5 Abs. 2
DSGVO. Ausloeser ist das Kommando ``praxiszeit-server.py reset-admin-password``,
das ein Konto lokal auf der Maschine uebernehmen kann; die Tabelle ist bewusst
allgemein gehalten (2FA-Abschaltung, kuenftige Vorgaenge derselben Klasse).

``tenant_id`` ist nullable: ein Vorgang kann die Infrastruktur betreffen, ohne
einem Mandanten zu gehoeren. Die RLS-Regel laesst solche Zeilen nur den
Superadmin sehen (``tenant_id = NULL`` erfuellt den Vergleich nie).

``subject_user_id`` ist ``ON DELETE SET NULL`` — sonst blockiert die Zeile den
Art.-17-Hard-Delete eines Nutzers (``admin_users.purge_user``), und genau dieser
Fall ist im Projekt bei #305 schon einmal eingetreten.

Revision ID: 071_security_events
Revises: 070_shift_plan_vis_note
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '071_security_events'
down_revision = '070_shift_plan_vis_note'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'security_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=True),
        sa.Column('event', sa.String(50), nullable=False),
        sa.Column('subject_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('actor', sa.String(200), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_security_events_tenant_id', 'security_events', ['tenant_id'])
    op.create_index('ix_security_events_event', 'security_events', ['event'])
    op.create_index('ix_security_events_created_at', 'security_events', ['created_at'])

    op.execute("ALTER TABLE security_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE security_events FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON security_events
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
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON security_events")
    op.drop_index('ix_security_events_created_at', table_name='security_events')
    op.drop_index('ix_security_events_event', table_name='security_events')
    op.drop_index('ix_security_events_tenant_id', table_name='security_events')
    op.drop_table('security_events')
