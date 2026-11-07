"""Aenderungsprotokoll als Beweismittel (#537, Audit 2026-11-07 A2-1/2/3/8).

``time_entry_audit_logs`` trug als Beleg nach § 16 Abs. 2 ArbZG nicht:

* A2-1: ``time_entry_id`` lag in der Pruefsumme, der Fremdschluessel ist
  ``ON DELETE SET NULL`` — jede Loeschung eines Zeiteintrags machte dessen
  Protokollzeilen fuer ``verify-integrity`` zu "manipuliert". Gleiches galt fuer
  ``change_request_id``. Ab hier gibt es unveraenderliche Kopien
  (``entry_ref``, ``changed_by_ref``, ``change_request_ref``), die beim Anlegen
  gesetzt und nie genullt werden; die Pruefsumme laeuft ueber sie. Der Backfill
  kopiert die heutigen Werte — Zeilen, deren Eintrag schon VOR dieser Migration
  geloescht wurde, bleiben uneindeutig (``legacy_entry_deleted``).
* A2-2: neue Zeilen tragen ``hash_version = 3``; die Pruefsumme deckt
  ``created_at`` und die Rohstempel ab. ``chain_seq``/``chain_prev``/
  ``chain_hash`` versiegeln die Zeilen je Mandant zu einer Kette (das Siegel
  setzt der taegliche Lauf bzw. die Pruefung), eine geloeschte Zeile hinterlaesst
  eine Luecke. Ein Trigger verweigert jedem Konto ausser der Eigentuemerin
  (Migrationsrolle) UPDATE und DELETE und laesst nur gehashte Neuzeilen zu; die
  App-Rolle verliert zusaetzlich die Rechte UPDATE/DELETE. Die drei erlaubten
  Aenderungen (Notiz-Scrub nach Art. 17, Versiegeln, Loeschen versiegelter
  Zeilen) laufen ueber SECURITY-DEFINER-Funktionen mit festem Zuschnitt.
* A2-3: die Rohstempel (``raw_start_time``/``raw_end_time``), das Ende der
  Anwesenheit und die nicht angerechneten Minuten stehen je Zeile vorher/nachher.
* A2-8: ``changed_by`` wird nullable mit ``ON DELETE SET NULL`` — die
  Endloeschung eines Verwalters haengt seine Zeilen nicht mehr auf den
  handelnden Verwalter um (das schrieb die Urheberschaft um), die Zeile zeigt
  "geloeschte Person"; ``changed_by_ref`` haelt die (zufaellige) Kennung fuer die
  Pruefsumme.

Downgrade: Funktionen, Trigger und Spalten fallen weg, die App-Rolle bekommt
UPDATE/DELETE zurueck. ``changed_by`` wird wieder NOT NULL — Zeilen, deren
Urheber endgeloescht wurde, bekommen dabei die betroffene Person als Urheber
(einziger gueltiger Verweis; nur fuer den Entwicklungs-Rueckweg gedacht).

Revision ID: 076_audit_chain
Revises: 075_contract_history
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "076_audit_chain"
down_revision = "075_contract_history"
branch_labels = None
depends_on = None

TABLE = "time_entry_audit_logs"
RAW_COLUMNS = (
    ("raw_start_time", sa.Time()),
    ("raw_end_time", sa.Time()),
    ("presence_end_time", sa.Time()),
    ("uncredited_minutes", sa.Integer()),
)

# Wer Eigentuemerin der Tabelle ist (oder Superuser), darf alles — Migrationen,
# Wiederherstellung (pg_restore laedt per COPY als Eigentuemerin) und die
# Fremdschluessel-Aktionen ON DELETE SET NULL (PostgreSQL fuehrt sie als
# Eigentuemerin der verweisenden Tabelle aus). Jedes andere Konto darf nur
# gehashte, unversiegelte Zeilen anfuegen.
GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    tbl_owner oid;
BEGIN
    SELECT relowner INTO tbl_owner FROM pg_class WHERE oid = TG_RELID;
    IF pg_has_role(current_user, tbl_owner, 'MEMBER')
       OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false) THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.row_hash IS NULL OR NEW.hash_version IS NULL THEN
            RAISE EXCEPTION 'time_entry_audit_logs: Zeile ohne Pruefsumme abgelehnt'
                USING ERRCODE = '42501';
        END IF;
        IF NEW.chain_seq IS NOT NULL OR NEW.chain_prev IS NOT NULL OR NEW.chain_hash IS NOT NULL THEN
            RAISE EXCEPTION 'time_entry_audit_logs: Kettenglied nur ueber pz_audit_seal'
                USING ERRCODE = '42501';
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'time_entry_audit_logs: % nur ueber die Protokollfunktionen erlaubt', TG_OP
        USING ERRCODE = '42501';
END $$;
"""

# Die drei erlaubten Aenderungen. SECURITY DEFINER = sie laufen als
# Eigentuemerin (der Trigger laesst sie durch); FORCE RLS gilt auch fuer die
# Eigentuemerin, die Mandantenregel greift also mit den Einstellungen der
# aufrufenden Sitzung — zusaetzlich prueft jede Funktion den Mandanten selbst.
# Mandantenpruefung der Funktionen. Noetig, obwohl FORCE RLS gilt: im Betrieb
# ist die Eigentuemerin (Migrationsrolle) Superuser und umgeht RLS — innerhalb
# einer SECURITY-DEFINER-Funktion also auch die App. Massgeblich ist die
# Sitzung (session_user): ist SIE Superuser (Wartung, Tests als Eigentuemerin),
# gilt keine Mandantengrenze — wie bei jedem direkten Zugriff.
TENANT_OK_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_tenant_ok(p_tenant uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT current_setting('app.is_superadmin', true) = 'true'
        OR p_tenant = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = session_user), false)
$$;
"""

SEAL_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_seal(p_ids uuid[], p_seqs bigint[], p_prevs text[], p_hashes text[])
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    n integer;
BEGIN
    UPDATE time_entry_audit_logs t
       SET chain_seq = s.seq, chain_prev = s.prev, chain_hash = s.h
      FROM unnest(p_ids, p_seqs, p_prevs, p_hashes) AS s(id, seq, prev, h)
     WHERE t.id = s.id
       AND t.chain_seq IS NULL
       AND pz_audit_tenant_ok(t.tenant_id);
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> COALESCE(array_length(p_ids, 1), 0) THEN
        RAISE EXCEPTION 'pz_audit_seal: % von % Zeilen versiegelt', n, COALESCE(array_length(p_ids, 1), 0);
    END IF;
    RETURN n;
END $$;
"""

NOTES_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_set_notes(p_id uuid, p_old_note text, p_new_note text, p_row_hash text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    UPDATE time_entry_audit_logs t
       SET old_note = p_old_note, new_note = p_new_note, row_hash = p_row_hash
     WHERE t.id = p_id
       AND pz_audit_tenant_ok(t.tenant_id);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'pz_audit_set_notes: Zeile % nicht gefunden', p_id;
    END IF;
END $$;
"""

DELETE_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_delete(p_ids uuid[])
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    n integer;
BEGIN
    IF EXISTS (SELECT 1 FROM time_entry_audit_logs
                WHERE id = ANY(p_ids) AND chain_seq IS NULL) THEN
        RAISE EXCEPTION 'pz_audit_delete: nur versiegelte Zeilen duerfen geloescht werden';
    END IF;
    DELETE FROM time_entry_audit_logs t
     WHERE t.id = ANY(p_ids)
       AND pz_audit_tenant_ok(t.tenant_id);
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;
"""

# Rechte UPDATE/DELETE jedem Konto ausser der Eigentuemerin entziehen (auch
# PUBLIC). Die Rolle der App heisst je Installation anders (APP_DB_USER bzw.
# [database] app_user), deshalb aus der Rechteliste der Tabelle gelesen.
REVOKE_BLOCK = """
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT DISTINCT a.grantee
          FROM pg_class c, aclexplode(c.relacl) a
         WHERE c.oid = 'public.time_entry_audit_logs'::regclass
           AND a.privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE')
           AND a.grantee <> c.relowner
    LOOP
        IF r.grantee = 0 THEN
            EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON time_entry_audit_logs FROM PUBLIC';
        ELSE
            EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON time_entry_audit_logs FROM %s',
                           r.grantee::regrole);
        END IF;
    END LOOP;
END $$;
"""


def _changed_by_fk_name(conn):
    for fk in sa.inspect(conn).get_foreign_keys(TABLE):
        if fk.get("constrained_columns") == ["changed_by"]:
            return fk.get("name")
    return None


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("entry_ref", UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("changed_by_ref", UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("change_request_ref", UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("hash_version", sa.SmallInteger(), nullable=True))
    for side in ("old", "new"):
        for name, type_ in RAW_COLUMNS:
            op.add_column(TABLE, sa.Column(f"{side}_{name}", type_, nullable=True))
    op.add_column(TABLE, sa.Column("chain_seq", sa.BigInteger(), nullable=True))
    op.add_column(TABLE, sa.Column("chain_prev", sa.String(64), nullable=True))
    op.add_column(TABLE, sa.Column("chain_hash", sa.String(64), nullable=True))
    op.create_index(
        "uq_audit_tenant_chain_seq", TABLE, ["tenant_id", "chain_seq"], unique=True,
    )
    op.create_index("ix_time_entry_audit_logs_entry_ref", TABLE, ["entry_ref"])

    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"
    if is_pg:
        # FORCE RLS: sonst trifft der Backfill still 0 Zeilen (Muster 073/075)
        conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))
    result = conn.execute(sa.text(
        "UPDATE time_entry_audit_logs SET entry_ref = time_entry_id, "
        "changed_by_ref = changed_by, change_request_ref = change_request_id"
    ))
    count = result.rowcount

    # A2-8: Urheber darf endgeloescht werden, die Zeile bleibt.
    fk_name = _changed_by_fk_name(conn)
    with op.batch_alter_table(TABLE) as batch:
        if fk_name:
            batch.drop_constraint(fk_name, type_="foreignkey")
        batch.alter_column("changed_by", existing_type=UUID(as_uuid=True), nullable=True)
        batch.create_foreign_key(
            "time_entry_audit_logs_changed_by_fkey", "users", ["changed_by"], ["id"],
            ondelete="SET NULL",
        )

    if is_pg:
        conn.execute(sa.text(GUARD_FUNCTION))
        conn.execute(sa.text(
            "CREATE TRIGGER pz_audit_guard_write BEFORE INSERT OR UPDATE OR DELETE "
            "ON time_entry_audit_logs FOR EACH ROW EXECUTE FUNCTION pz_audit_guard()"
        ))
        for fn in (TENANT_OK_FUNCTION, SEAL_FUNCTION, NOTES_FUNCTION, DELETE_FUNCTION):
            conn.execute(sa.text(fn))
        conn.execute(sa.text(REVOKE_BLOCK))

    try:
        print(f"076: {count} Protokollzeilen mit festen Verweisen versehen")
    except UnicodeEncodeError:  # pragma: no cover - Windows-Konsole
        print(f"076: {count} Protokollzeilen")


def downgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"
    if is_pg:
        conn.execute(sa.text("DROP TRIGGER IF EXISTS pz_audit_guard_write ON time_entry_audit_logs"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_guard()"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_seal(uuid[], bigint[], text[], text[])"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_set_notes(uuid, text, text, text)"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_delete(uuid[])"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_tenant_ok(uuid)"))
        conn.execute(sa.text(
            "DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'praxiszeit_app') THEN "
            "GRANT UPDATE, DELETE ON time_entry_audit_logs TO praxiszeit_app; END IF; END $$;"
        ))
        conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))
    conn.execute(sa.text(
        "UPDATE time_entry_audit_logs SET changed_by = user_id WHERE changed_by IS NULL"
    ))
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint("time_entry_audit_logs_changed_by_fkey", type_="foreignkey")
        batch.alter_column("changed_by", existing_type=UUID(as_uuid=True), nullable=False)
        batch.create_foreign_key(
            "time_entry_audit_logs_changed_by_fkey", "users", ["changed_by"], ["id"],
        )

    op.drop_index("ix_time_entry_audit_logs_entry_ref", table_name=TABLE)
    op.drop_index("uq_audit_tenant_chain_seq", table_name=TABLE)
    for name in ("chain_hash", "chain_prev", "chain_seq"):
        op.drop_column(TABLE, name)
    for side in ("new", "old"):
        for name, _ in reversed(RAW_COLUMNS):
            op.drop_column(TABLE, f"{side}_{name}")
    for name in ("hash_version", "change_request_ref", "changed_by_ref", "entry_ref"):
        op.drop_column(TABLE, name)
