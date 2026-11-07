"""#537 (Postgres-only): Migration 076 — Aenderungsprotokoll nur noch anfuegbar.

Laeuft in einer EIGENEN Wegwerf-Datenbank (``CREATE DATABASE`` als Superuser),
mit einer eigenen App-Rolle ohne Superuser- und BYPASSRLS-Recht, die wie im
Betrieb vor 076 SELECT/INSERT/UPDATE/DELETE auf allen Tabellen hat
(``init-db-user.sql``). Geprueft wird, was SQLite nie zeigt:

* nach 076 darf die App-Rolle ``time_entry_audit_logs`` weder aendern noch
  loeschen — auch dann nicht, wenn ein erneuter Lauf von ``init-db-user.sql``
  (Wiederherstellung, CI) die Rechte wieder vergibt (Trigger);
* sie darf nur gehashte, unversiegelte Zeilen anfuegen;
* das Loeschen eines Zeiteintrags (ON DELETE SET NULL, laeuft als
  Eigentuemerin) und eines Urhebers funktioniert weiter und bricht die
  Pruefsumme nicht (A2-1, A2-8);
* die drei erlaubten Aenderungen (Versiegeln, Notiz-Scrub, Loeschen
  versiegelter Zeilen) gehen als App-Rolle ueber ``audit_chain_service``, die
  Mandantentrennung greift in den Funktionen;
* Backfill der festen Verweise, Downgrade und erneutes Upgrade.

Eingehaengt in ``scripts/local-ci.sh`` Schritt 2 und den PostgreSQL-Schritt von
``.github/workflows/cross-tenant-ci.yml`` (im SQLite-Schritt per ``--ignore``).
"""
import os
import secrets
import uuid
from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from tests.pg_migration_helpers import alembic as _alembic, scratch_database

ADMIN_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_URL or not ADMIN_URL.startswith("postgresql"):
    pytest.skip(
        "test_076_audit_chain_pg.py braucht PostgreSQL (ADMIN_DB_URL / DATABASE_URL_MIGRATIONS)",
        allow_module_level=True,
    )

BACKEND = Path(__file__).resolve().parents[1]
TENANT = "00000000-0000-0000-0000-000000000001"  # legt Migration 027 an
OTHER_TENANT = "00000000-0000-0000-0000-0000000076aa"
BASE_REV = "075_contract_history"
HEAD_REV = "076_audit_chain"
EMP = str(uuid.UUID(int=0x7676_0000_0000_4000_8000_0000_0000_0001))
ADM = str(uuid.UUID(int=0x7676_0000_0000_4000_8000_0000_0000_0002))
ENTRY = str(uuid.UUID(int=0x7676_0000_0000_4000_8000_0000_0000_0003))
LEGACY = str(uuid.UUID(int=0x7676_0000_0000_4000_8000_0000_0000_0004))


@pytest.fixture
def env():
    """(owner_url, app_url) — Wegwerf-DB auf Stand 075 mit Altbestand, App-Rolle
    mit den Rechten aus init-db-user.sql, dann Upgrade auf 076."""
    role = f"pz076_app_{uuid.uuid4().hex[:10]}"
    password = secrets.token_hex(16)
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(
                f"CREATE ROLE \"{role}\" LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT PASSWORD '{password}'"))
        with scratch_database(ADMIN_URL, "pz076") as (url, engine):
            _alembic(url, "upgrade", BASE_REV)
            with engine.begin() as conn:
                conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
                conn.execute(text(
                    f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'))
                _seed_075(conn)
            _alembic(url, "upgrade", HEAD_REV)
            app_url = make_url(url).set(username=role, password=password).render_as_string(
                hide_password=False)
            yield url, engine, app_url, role
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()


def _seed_075(conn):
    conn.execute(text("SET LOCAL app.is_superadmin = 'true'"))
    for uid, name, role in ((EMP, "emp076", "EMPLOYEE"), (ADM, "adm076", "ADMIN")):
        conn.execute(text(
            "INSERT INTO users (id, tenant_id, username, email, password_hash, first_name, "
            "last_name, role, weekly_hours, is_active, vacation_days, track_hours, "
            "milog_working_time_account, use_fixed_monthly_target) VALUES (:id, :t, :u, :e, 'h', "
            ":u, 'T', :r, 40, true, 30, true, false, false)"), {"id": uid, "t": TENANT, "u": name, "e": f"{name}@x.de", "r": role})
    conn.execute(text(
        "INSERT INTO time_entries (id, tenant_id, user_id, date, start_time, end_time, "
        "break_minutes) VALUES (:id, :t, :u, '2026-03-02', '08:00', '16:00', 30)"),
        {"id": ENTRY, "t": TENANT, "u": EMP})
    # Altbestand (v2): Zeile am Eintrag, Hash wie vor 076
    conn.execute(text(
        "INSERT INTO time_entry_audit_logs (id, tenant_id, time_entry_id, user_id, changed_by, "
        "action, source, new_date, new_start_time, new_end_time, row_hash) VALUES "
        "(:id, :t, :e, :u, :a, 'create', 'manual', '2026-03-02', '08:00', '16:00', NULL)"),
        {"id": LEGACY, "t": TENANT, "e": ENTRY, "u": EMP, "a": ADM})


def _app_session(app_url, tenant=TENANT):
    eng = create_engine(app_url)
    s = sessionmaker(bind=eng)()
    s.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": tenant})
    return eng, s


def _insert_hashed(session, **kw):
    from app.models import TimeEntryAuditLog
    row = TimeEntryAuditLog(tenant_id=uuid.UUID(TENANT), user_id=uuid.UUID(EMP),
                            changed_by=uuid.UUID(ADM), action="update", source="manual",
                            new_date=date(2026, 3, 2), new_start_time=time(8, 0), **kw)
    session.add(row)
    session.commit()
    return row


def _expect_denied(session, sql, params=None):
    with pytest.raises(DBAPIError) as exc:
        session.execute(text(sql), params or {})
        session.commit()
    session.rollback()
    return str(exc.value)


def test_backfill_and_grants(env):
    url, engine, _app_url, role = env
    with engine.connect() as conn:
        conn.execute(text("SET app.is_superadmin = 'true'"))
        ref = conn.execute(text(
            "SELECT entry_ref, changed_by_ref FROM time_entry_audit_logs WHERE id = :i"),
            {"i": LEGACY}).one()
        assert (str(ref[0]), str(ref[1])) == (ENTRY, ADM)
        privs = {p for (p,) in conn.execute(text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_name = 'time_entry_audit_logs' AND grantee = :r"), {"r": role})}
        assert privs == {"SELECT", "INSERT"}
        nullable = conn.execute(text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'time_entry_audit_logs' AND column_name = 'changed_by'")).scalar()
        assert nullable == "YES"


def test_app_role_cannot_update_or_delete_even_after_regrant(env):
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        row = _insert_hashed(s)
        _expect_denied(s, "UPDATE time_entry_audit_logs SET new_note = 'x' WHERE id = :i", {"i": str(row.id)})
        _expect_denied(s, "DELETE FROM time_entry_audit_logs WHERE id = :i", {"i": str(row.id)})
        # Wiederherstellung/CI fuehren init-db-user.sql erneut aus → Rechte wieder da
        with engine.begin() as conn:
            conn.execute(text(f'GRANT UPDATE, DELETE ON time_entry_audit_logs TO "{role}"'))
        msg = _expect_denied(s, "UPDATE time_entry_audit_logs SET new_note = 'x' WHERE id = :i",
                             {"i": str(row.id)})
        assert "Protokollfunktionen" in msg
        _expect_denied(s, "DELETE FROM time_entry_audit_logs WHERE id = :i", {"i": str(row.id)})
        # ungehashte Zeile anfuegen → abgelehnt
        msg = _expect_denied(s, (
            "INSERT INTO time_entry_audit_logs (id, tenant_id, user_id, changed_by, action, source) "
            "VALUES (gen_random_uuid(), :t, :u, :a, 'update', 'manual')"),
            {"t": TENANT, "u": EMP, "a": ADM})
        assert "Pruefsumme" in msg
    finally:
        s.close()
        eng.dispose()


def test_init_db_user_sql_revokes_again(env):
    url, engine, app_url, role = env
    sql = (BACKEND / "init-db-user.sql").read_text().replace("praxiszeit_app", role)
    sql = sql.replace("GRANT CONNECT ON DATABASE praxiszeit", "-- ")
    with engine.begin() as conn:
        # wie die Default-Privilegien beim Anlegen: auch die Eigentuemer-Tabellen
        conn.exec_driver_sql(f'GRANT ALL ON audit_log_ids, audit_log_tombstones TO "{role}"')
        conn.exec_driver_sql(sql)
        privs = {p for (p,) in conn.execute(text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_name = 'time_entry_audit_logs' AND grantee = :r"), {"r": role})}
        owner_only = {p for (p,) in conn.execute(text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_name IN ('audit_log_ids', 'audit_log_tombstones') AND grantee = :r"),
            {"r": role})}
    assert "UPDATE" not in privs and "DELETE" not in privs
    assert owner_only == set()


def test_entry_and_author_deletion_keep_hash(env):
    """A2-1/A2-8: ON DELETE SET NULL laeuft als Eigentuemerin durch den Trigger,
    die v3-Pruefsumme bleibt gueltig."""
    from app.core import audit_integrity
    from app.models import TimeEntryAuditLog
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        row = _insert_hashed(s, time_entry_id=uuid.UUID(ENTRY))
        s.execute(text("DELETE FROM time_entries WHERE id = :i"), {"i": ENTRY})
        s.commit()
        s.expire_all()
        fresh = s.get(TimeEntryAuditLog, row.id)
        assert fresh.time_entry_id is None and str(fresh.entry_ref) == ENTRY
        assert audit_integrity.verify_row(fresh)
        # Altbestand: v2 gegen die Kopie aus dem Backfill — Loeschung bricht nichts
        legacy = s.get(TimeEntryAuditLog, uuid.UUID(LEGACY))
        assert legacy.time_entry_id is None and legacy.hash_version is None
        # Urheber endgeloescht → changed_by NULL, Zeile bleibt pruefbar
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.is_superadmin = 'true'"))
            conn.execute(text("DELETE FROM time_entry_audit_logs WHERE user_id = :a"), {"a": ADM})
            conn.execute(text("DELETE FROM users WHERE id = :a"), {"a": ADM})
        s.expire_all()
        fresh = s.get(TimeEntryAuditLog, row.id)
        assert fresh.changed_by is None and str(fresh.changed_by_ref) == ADM
        assert audit_integrity.verify_row(fresh)
    finally:
        s.close()
        eng.dispose()


def test_service_paths_work_as_app_role(env):
    """Versiegeln, Scrub und legitimes Loeschen als App-Rolle; danach intakt."""
    from app.core import audit_integrity
    from app.services import audit_chain_service
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        rows = [_insert_hashed(s, new_note=f"n{i}") for i in range(3)]
        assert audit_chain_service.seal_chain(s, uuid.UUID(TENANT)) >= 3
        s.commit()
        s.expire_all()
        assert all(r.chain_seq is not None for r in rows)
        audit_chain_service.set_notes(s, rows[0], None, "[anonymisiert]")
        s.commit()
        s.expire_all()
        assert rows[0].new_note == "[anonymisiert]" and audit_integrity.verify_row(rows[0])
        n = audit_chain_service.delete_rows(
            s, [rows[1]], tenant_id=uuid.UUID(TENANT), user_id=uuid.UUID(EMP),
            changed_by=uuid.UUID(ADM), source="dsgvo", reason="Test")
        s.commit()
        assert n == 1
        result = audit_chain_service.check_tenant(s, uuid.UUID(TENANT), actor="t", record_failure=False)
        assert result["intact"], result
        assert result["legacy_unhashed"] == 1  # Altbestand ohne Hash, aelter als alles andere
    finally:
        s.close()
        eng.dispose()


def test_functions_respect_tenant_and_seal_once(env):
    from app.services import audit_chain_service
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        row = _insert_hashed(s)
        row_id = str(row.id)
        audit_chain_service.seal_chain(s, uuid.UUID(TENANT))
        s.commit()
        # zweites Versiegeln derselben Zeile → abgelehnt (write-once)
        _expect_denied(s, "SELECT pz_audit_seal(ARRAY[CAST(:i AS uuid)], ARRAY[99::bigint], "
                          "ARRAY[''], ARRAY['x'])", {"i": row_id})
        # unversiegelte Zeile darf nicht geloescht werden
        loose = _insert_hashed(s)
        _expect_denied(s, "SELECT pz_audit_delete(ARRAY[CAST(:i AS uuid)])", {"i": str(loose.id)})
    finally:
        s.close()
        eng.dispose()
    eng, other = _app_session(app_url, tenant=OTHER_TENANT)
    try:
        # fremder Mandant: die Funktion sieht die Zeile nicht
        _expect_denied(other, "SELECT pz_audit_set_notes(CAST(:i AS uuid), NULL, 'x', NULL)",
                       {"i": row_id})
        assert other.execute(text("SELECT pz_audit_delete(ARRAY[CAST(:i AS uuid)])"),
                             {"i": row_id}).scalar() == 0
        other.rollback()
    finally:
        other.close()
        eng.dispose()


def _head_seq(engine):
    with engine.connect() as conn:
        conn.execute(text("SET app.is_superadmin = 'true'"))
        return conn.execute(text("SELECT pz_audit_head_seq(:t)"), {"t": TENANT}).scalar()


def test_head_row_cannot_be_deleted_or_renamed_by_app_role(env):
    """Review-Runde: ohne Kettenende fiele das Abschneiden der letzten Glieder
    nicht auf — die App-Rolle darf es nicht entfernen; fortgeschrieben wird es
    ueber pz_audit_set_head."""
    from app.services import audit_chain_service
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        _insert_hashed(s)
        audit_chain_service.seal_chain(s, uuid.UUID(TENANT))
        s.commit()
        msg = _expect_denied(s, "DELETE FROM system_settings WHERE key = 'audit_chain_head'")
        assert "Kettenende" in msg
        _expect_denied(s, "UPDATE system_settings SET key = 'weg' WHERE key = 'audit_chain_head'")
        # Fortschreiben (naechstes Versiegeln) geht weiter
        _insert_hashed(s)
        assert audit_chain_service.seal_chain(s, uuid.UUID(TENANT)) == 1
        s.commit()
        # andere Einstellungen bleiben loeschbar
        s.execute(text("INSERT INTO system_settings (key, tenant_id, value) VALUES ('x076', :t, '1')"),
                  {"t": TENANT})
        s.execute(text("DELETE FROM system_settings WHERE key = 'x076'"))
        s.commit()
    finally:
        s.close()
        eng.dispose()


def test_seal_then_delete_of_fresh_row_is_refused(env):
    """Frische Zeile selbst versiegeln und gleich loeschen: Versiegeln nur
    lueckenlos ab dem Kettenende, Loeschen nur bis zum Kettenende."""
    from app.services import audit_chain_service
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        _insert_hashed(s)
        audit_chain_service.seal_chain(s, uuid.UUID(TENANT))
        s.commit()
        head = _head_seq(engine)
        fresh = _insert_hashed(s)
        # Luecke lassen → abgelehnt
        msg = _expect_denied(s, "SELECT pz_audit_seal(ARRAY[CAST(:i AS uuid)], ARRAY[CAST(:q AS bigint)], "
                                "ARRAY[''], ARRAY['x'])", {"i": str(fresh.id), "q": head + 5})
        assert "lueckenlos" in msg
        # lueckenlos mit Unsinns-Hash: geht, aber loeschen nicht (hinter dem Kettenende)
        s.execute(text("SELECT pz_audit_seal(ARRAY[CAST(:i AS uuid)], ARRAY[CAST(:q AS bigint)], "
                       "ARRAY[''], ARRAY['x'])"), {"i": str(fresh.id), "q": head + 1})
        s.commit()
        msg = _expect_denied(s, "SELECT pz_audit_delete(ARRAY[CAST(:i AS uuid)])", {"i": str(fresh.id)})
        assert "Kettenende" in msg
        # und die Pruefung sieht das falsche Glied
        result = audit_chain_service.verify_tenant(s, uuid.UUID(TENANT))
        assert str(fresh.id) in result["tampered_ids"]
    finally:
        s.close()
        eng.dispose()


def test_delete_refused_without_head(env):
    from app.services import audit_chain_service
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        row = _insert_hashed(s)
        audit_chain_service.seal_chain(s, uuid.UUID(TENANT))
        s.commit()
        with engine.begin() as conn:  # Eigentuemerin darf (Wartung)
            conn.execute(text("SET LOCAL app.is_superadmin = 'true'"))
            conn.execute(text("DELETE FROM system_settings WHERE key = 'audit_chain_head'"))
        _expect_denied(s, "SELECT pz_audit_delete(ARRAY[CAST(:i AS uuid)])", {"i": str(row.id)})
        with pytest.raises(audit_chain_service.AuditChainBroken):
            audit_chain_service.seal_chain(s, uuid.UUID(TENANT))
        s.rollback()
    finally:
        s.close()
        eng.dispose()


def test_functions_not_executable_by_public(env):
    url, engine, app_url, role = env
    other = f"pz076_x_{uuid.uuid4().hex[:8]}"
    with engine.begin() as conn:
        conn.execute(text(f'CREATE ROLE "{other}" NOLOGIN'))
    try:
        with engine.connect() as conn:
            for fn in ("pz_audit_seal(uuid[], bigint[], text[], text[])", "pz_audit_delete(uuid[])",
                       "pz_audit_set_notes(uuid, text, text, text)", "pz_audit_head_seq(uuid)"):
                assert conn.execute(text("SELECT has_function_privilege(:r, :f, 'EXECUTE')"),
                                    {"r": role, "f": fn}).scalar(), fn
                assert not conn.execute(text("SELECT has_function_privilege(:r, :f, 'EXECUTE')"),
                                        {"r": other, "f": fn}).scalar(), fn
        # init-db-user.sql (Wiederherstellung) laesst es so
        sql = (BACKEND / "init-db-user.sql").read_text().replace("praxiszeit_app", role)
        sql = sql.replace("GRANT CONNECT ON DATABASE praxiszeit", "-- ")
        with engine.begin() as conn:
            conn.exec_driver_sql(sql)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT has_function_privilege(:r, 'pz_audit_delete(uuid[])', 'EXECUTE')"),
                                {"r": role}).scalar()
            assert not conn.execute(text("SELECT has_function_privilege(:r, 'pz_audit_delete(uuid[])', 'EXECUTE')"),
                                    {"r": other}).scalar()
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP ROLE IF EXISTS "{other}"'))


def test_downgrade_and_upgrade_again(env):
    url, engine, app_url, role = env
    _alembic(url, "downgrade", BASE_REV)
    with engine.connect() as conn:
        cols = {c for (c,) in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'time_entry_audit_logs'"))}
        assert "entry_ref" not in cols and "chain_seq" not in cols
        assert conn.execute(text(
            "SELECT count(*) FROM pg_proc WHERE proname LIKE 'pz_audit_%'")).scalar() == 0
        assert conn.execute(text(
            "SELECT to_regclass('public.audit_log_ids') IS NULL")).scalar() is True
        assert conn.execute(text(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'pz_audit_head_guard_write'")).scalar() == 0
    _alembic(url, "upgrade", HEAD_REV)
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'pz_audit_guard_write'")).scalar() == 1
        assert conn.execute(text(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'pz_audit_head_guard_write'")).scalar() == 1


# ── Review-Runde 2 (2026-11-07): Kettenende, Notiz-Scrub, Altbestandsgrenze ──

def _head_value(engine):
    with engine.connect() as conn:
        conn.execute(text("SET app.is_superadmin = 'true'"))
        return conn.execute(text(
            "SELECT value FROM system_settings WHERE key = 'audit_chain_head' AND tenant_id = :t"),
            {"t": TENANT}).scalar()


def _make_other_tenant(engine):
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL app.is_superadmin = 'true'"))
        conn.execute(text(
            "INSERT INTO tenants (id, name, slug, is_active, mode, plan, subscription_status) "
            "VALUES (:t, 'Andere', 'andere076', true, 'multi', 'trial', 'active') "
            "ON CONFLICT (id) DO NOTHING"), {"t": OTHER_TENANT})


def test_app_role_cannot_write_head_directly(env):
    """Das Kettenende bewegt nur pz_audit_set_head — ein direktes UPDATE der
    App-Rolle (z. B. Rueckspielen eines aelteren Kopfs oder Hochsetzen, um
    pz_audit_delete mehr Glieder freizugeben) wird abgelehnt."""
    from app.services import audit_chain_service
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        for _ in range(2):
            _insert_hashed(s)
        audit_chain_service.seal_chain(s, uuid.UUID(TENANT))
        s.commit()
        value = _head_value(engine)
        msg = _expect_denied(s, "UPDATE system_settings SET value = :v WHERE key = 'audit_chain_head'",
                             {"v": "999:" + value.split(":", 1)[1]})
        assert "Kettenende" in msg
        _expect_denied(s, "UPDATE system_settings SET value = value WHERE key = 'audit_chain_head'")
        # Einfuegen (Mandant ohne Kopf) / Umbenennen einer anderen Zeile
        _make_other_tenant(engine)
        eng2, o = _app_session(app_url, tenant=OTHER_TENANT)
        try:
            msg = _expect_denied(o, "INSERT INTO system_settings (key, tenant_id, value) "
                                    "VALUES ('audit_chain_head', :t, '0::00')", {"t": OTHER_TENANT})
            assert "Kettenende" in msg
        finally:
            o.close()
            eng2.dispose()
        s.execute(text("INSERT INTO system_settings (key, tenant_id, value) VALUES ('y076', :t, '1')"),
                  {"t": TENANT})
        s.commit()
        msg = _expect_denied(s, "UPDATE system_settings SET key = 'audit_chain_head' WHERE key = 'y076'")
        assert "Kettenende" in msg
        assert _head_value(engine) == value
    finally:
        s.close()
        eng.dispose()


def test_set_head_only_to_the_current_top_link(env):
    """pz_audit_set_head: nur auf das hoechste versiegelte Glied, nie zurueck."""
    from app.services import audit_chain_service
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        for _ in range(3):
            _insert_hashed(s)
        audit_chain_service.seal_chain(s, uuid.UUID(TENANT))
        s.commit()
        seq, h, _mac = _head_value(engine).split(":")
        seq = int(seq)
        # weiter hinaus, als Glieder existieren → abgelehnt
        _expect_denied(s, "SELECT pz_audit_set_head(:t, :v, false)",
                       {"t": TENANT, "v": f"{seq + 50}:{h}:00"})
        # falscher Hash fuer das hoechste Glied → abgelehnt
        _expect_denied(s, "SELECT pz_audit_set_head(:t, :v, false)",
                       {"t": TENANT, "v": f"{seq}:{'0' * 64}:00"})
        # Glied loeschen (legitim), dann den Kopf zurueckdrehen → abgelehnt
        top = s.execute(text(
            "SELECT id FROM time_entry_audit_logs WHERE tenant_id = :t AND chain_seq = :q"),
            {"t": TENANT, "q": seq}).scalar()
        prev_hash = s.execute(text(
            "SELECT chain_hash FROM time_entry_audit_logs WHERE tenant_id = :t AND chain_seq = :q"),
            {"t": TENANT, "q": seq - 1}).scalar()
        s.execute(text("SELECT pz_audit_delete(ARRAY[CAST(:i AS uuid)])"), {"i": str(top)})
        s.commit()
        msg = _expect_denied(s, "SELECT pz_audit_set_head(:t, :v, false)",
                             {"t": TENANT, "v": f"{seq - 1}:{prev_hash}:00"})
        assert "zurueck" in msg
        # auch "Neu setzen" ohne Vermerk-Zeile darf nicht zurueck
        _expect_denied(s, "SELECT pz_audit_set_head(:t, :v, true)",
                       {"t": TENANT, "v": f"{seq - 1}:{prev_hash}:00"})
        assert int(_head_value(engine).split(":")[0]) == seq
        # die Pruefung sieht die Loeschung ohne Vermerk
        result = audit_chain_service.verify_tenant(s, uuid.UUID(TENANT))
        assert not result["intact"] and seq in result["missing_seqs"], result
    finally:
        s.close()
        eng.dispose()


def test_set_notes_cannot_strip_hash_or_write_free_text(env):
    from app.services import audit_chain_service
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        row = _insert_hashed(s, new_note="Vertretung fuer maria@x.de", old_note="alt")
        rid = str(row.id)
        stored = row.row_hash
        # Pruefsumme entfernen (Herabstufung zu "Altbestand") → abgelehnt
        msg = _expect_denied(s, "SELECT pz_audit_set_notes(CAST(:i AS uuid), NULL, NULL, NULL)", {"i": rid})
        assert "Pruefsumme" in msg
        # freier Text statt Scrub → abgelehnt
        msg = _expect_denied(s, "SELECT pz_audit_set_notes(CAST(:i AS uuid), 'alt', 'umgeschrieben', :h)",
                             {"i": rid, "h": stored})
        assert "Anonymisierung" in msg
        # Teil-Ersetzung durch die Kennzeichnung, Pseudonym, Leeren: erlaubt
        audit_chain_service.set_notes(s, row, "alt", "Vertretung fuer [anonymisiert]")
        s.commit()
        audit_chain_service.set_notes(s, row, "deleted_0a1b2c3d", "Vertretung fuer [anonymisiert]")
        s.commit()
        audit_chain_service.set_notes(s, row, None, None)
        s.commit()
        # ungehashte Altzeile bekommt keinen (frei gewaehlten) Hash
        msg = _expect_denied(s, "SELECT pz_audit_set_notes(CAST(:i AS uuid), NULL, NULL, 'ab')",
                             {"i": LEGACY})
        assert "Pruefsumme" in msg
    finally:
        s.close()
        eng.dispose()


def test_legacy_cutoff_is_fixed_at_migration(env):
    """Die Grenze fuer Altbestand ohne Pruefsumme steht ab 076 fest in
    system_settings (nicht MIN(created_at) der gehashten Zeilen) — und die
    App-Rolle kann sie weder aendern, loeschen noch anlegen."""
    url, engine, app_url, role = env
    with engine.connect() as conn:
        conn.execute(text("SET app.is_superadmin = 'true'"))
        cutoff = conn.execute(text(
            "SELECT value FROM system_settings WHERE key = 'audit_legacy_cutoff' AND tenant_id = :t"),
            {"t": TENANT}).scalar()
        legacy_at = conn.execute(text(
            "SELECT created_at FROM time_entry_audit_logs WHERE id = :i"), {"i": LEGACY}).scalar()
    from app.core import audit_integrity
    assert cutoff is not None and cutoff >= audit_integrity.canonical_timestamp(legacy_at)
    eng, s = _app_session(app_url)
    try:
        s.commit()  # Mandanten-Kontext festschreiben (ein Rollback nimmt ihn sonst zurueck)
        assert s.execute(text("SELECT count(*) FROM system_settings "
                              "WHERE key = 'audit_legacy_cutoff'")).scalar() == 1
        _expect_denied(s, "UPDATE system_settings SET value = '2999-01-01T00:00:00.000000' "
                          "WHERE key = 'audit_legacy_cutoff'")
        _expect_denied(s, "DELETE FROM system_settings WHERE key = 'audit_legacy_cutoff'")
    finally:
        s.close()
        eng.dispose()
    _make_other_tenant(engine)
    eng, o = _app_session(app_url, tenant=OTHER_TENANT)
    try:
        msg = _expect_denied(o, "INSERT INTO system_settings (key, tenant_id, value) "
                                "VALUES ('audit_legacy_cutoff', :t, '2999-01-01')", {"t": OTHER_TENANT})
        assert "Altbestandsgrenze" in msg
    finally:
        o.close()
        eng.dispose()


# ── Review-Runde 3 (2026-11-07): geloeschte Zeilen kehren nie zurueck ──

def _reanchor_then_more_rows(s, engine):
    """Kette mit 3 Gliedern, Kettenende-Siegel gebrochen, Verwaltung setzt neu
    (echter Vermerk), dann zwei belastende Zeilen. Liefert den alten Kopf."""
    from app.services import audit_chain_service as acs
    t = uuid.UUID(TENANT)
    for _ in range(3):
        _insert_hashed(s)
    acs.seal_chain(s, t)
    s.commit()
    old_head = _head_value(engine)
    seq, h, _mac = old_head.split(":")
    s.execute(text("SELECT pz_audit_set_head(:t, :v, false)"), {"t": TENANT, "v": f"{seq}:{h}:00"})
    s.commit()
    acs.reanchor_chain(s, t, changed_by=uuid.UUID(ADM), reason="Pruefung")
    for _ in range(2):
        _insert_hashed(s, new_note="belastend")
    acs.seal_chain(s, t)
    s.commit()
    assert acs.verify_tenant(s, t)["intact"]
    return old_head, int(seq)


def test_replayed_reanchor_marker_cannot_rewind_the_head(env):
    """Angriff aus dem Review: alle Glieder hinter einem alten Kopf ueber
    pz_audit_delete entfernen (darunter den echten Vermerk), den Vermerk Byte
    fuer Byte wieder einfuegen und den alten Kopf zurueckspielen. Vorher galt die
    Kette danach als intakt, die belastenden Zeilen waren spurlos weg. Jetzt
    scheitert das Wiedereinfuegen an den Grabsteinen."""
    from app.services import audit_chain_service as acs
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        old_head, seq = _reanchor_then_more_rows(s, engine)
        rows = s.execute(text(
            "SELECT * FROM time_entry_audit_logs WHERE tenant_id = :t AND chain_seq > :q "
            "ORDER BY chain_seq"), {"t": TENANT, "q": seq}).mappings().all()
        marker = [dict(r) for r in rows if r["action"] == "audit_chain_reanchored"][0]
        s.execute(text("SELECT pz_audit_delete(CAST(:ids AS uuid[]))"),
                  {"ids": [str(r["id"]) for r in rows]})
        s.commit()
        cols = [k for k in marker if k not in ("chain_seq", "chain_prev", "chain_hash")]
        msg = _expect_denied(s, f"INSERT INTO time_entry_audit_logs ({', '.join(cols)}) VALUES "
                                f"({', '.join(':' + c for c in cols)})", {c: marker[c] for c in cols})
        assert "nicht zurueckkehren" in msg
        # ohne Vermerk darf der Kopf nicht zurueck
        msg = _expect_denied(s, "SELECT pz_audit_set_head(:t, :v, true)", {"t": TENANT, "v": old_head})
        assert "zurueck" in msg
        # die Loeschung ohne Vermerk bleibt sichtbar
        result = acs.verify_tenant(s, uuid.UUID(TENANT))
        assert not result["intact"] and result["missing_links"] > 0, result
    finally:
        s.close()
        eng.dispose()


def test_purged_row_cannot_be_reinserted(env):
    """Auch eine legitim (Art. 17, Aufbewahrungsfrist) entfernte Zeile kehrt
    nicht mit gueltigem Hash zurueck."""
    from app.services import audit_chain_service as acs
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        row = _insert_hashed(s, new_note="Art. 17")
        copy = dict(s.execute(text("SELECT * FROM time_entry_audit_logs WHERE id = :i"),
                              {"i": str(row.id)}).mappings().one())
        acs.delete_rows(s, [row], tenant_id=uuid.UUID(TENANT), user_id=uuid.UUID(EMP),
                        changed_by=uuid.UUID(ADM), source="dsgvo", reason="Test")
        s.commit()
        cols = [k for k in copy if k not in ("chain_seq", "chain_prev", "chain_hash")]
        msg = _expect_denied(s, f"INSERT INTO time_entry_audit_logs ({', '.join(cols)}) VALUES "
                                f"({', '.join(':' + c for c in cols)})", {c: copy[c] for c in cols})
        assert "nicht zurueckkehren" in msg
        # die Grabsteine sind fuer die App-Rolle unsichtbar und unveraenderlich
        _expect_denied(s, "SELECT count(*) FROM audit_log_tombstones")
        _expect_denied(s, "DELETE FROM audit_log_tombstones")
        with engine.connect() as conn:
            privs = {p for (p,) in conn.execute(text(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE table_name = 'audit_log_tombstones' AND grantee = :r"), {"r": role})}
        assert privs == set()
    finally:
        s.close()
        eng.dispose()


# ── Review-Runde 5: "eine id kehrt nie zurueck" haengt am Primaerschluessel ──

def test_reinsert_racing_an_uncommitted_delete_is_refused(env):
    """Zwei Verbindungen der App-Rolle: A loescht eine versiegelte Zeile ueber
    pz_audit_delete (noch ohne Commit), B fuegt dieselbe Zeile wieder ein. Der
    Grabstein-Blick in pz_audit_guard sah A's offenen Grabstein nicht, B wartete
    nur am Primaerschluessel und kam nach A's Commit durch. Jetzt scheitert B an
    der schon vergebenen id (audit_log_ids) - auch nach A's Commit."""
    import threading
    from app.services import audit_chain_service as acs
    url, engine, app_url, role = env
    eng_a, a = _app_session(app_url)
    eng_b, b = _app_session(app_url)
    try:
        row_id = str(_insert_hashed(a).id)
        acs.seal_chain(a, uuid.UUID(TENANT))
        a.commit()
        copy = dict(a.execute(text("SELECT * FROM time_entry_audit_logs WHERE id = :i"),
                              {"i": row_id}).mappings().one())
        b.commit()  # Mandanten-Kontext von B festschreiben
        cols = [k for k in copy if k not in ("chain_seq", "chain_prev", "chain_hash")]
        deleted = a.execute(text("SELECT pz_audit_delete(ARRAY[CAST(:i AS uuid)])"),
                            {"i": row_id}).scalar()
        assert deleted == 1  # A haelt die Loeschung offen

        result = {}

        def reinsert():
            try:
                b.execute(text(f"INSERT INTO time_entry_audit_logs ({', '.join(cols)}) VALUES "
                               f"({', '.join(':' + c for c in cols)})"), {c: copy[c] for c in cols})
                b.commit()
                result["ok"] = True
            except DBAPIError as exc:
                b.rollback()
                result["error"] = str(exc)

        worker = threading.Thread(target=reinsert)
        worker.start()
        worker.join(timeout=2)  # vorher: B blockiert hier am Primaerschluessel
        a.commit()
        worker.join(timeout=30)
        assert not worker.is_alive()
        assert "error" in result, "geloeschte Zeile kam zurueck"
        assert "nicht zurueckkehren" in result["error"]
        with engine.connect() as conn:
            conn.execute(text("SET app.is_superadmin = 'true'"))
            assert conn.execute(text("SELECT count(*) FROM time_entry_audit_logs WHERE id = :i"),
                                {"i": row_id}).scalar() == 0
    finally:
        a.close()
        b.close()
        eng_a.dispose()
        eng_b.dispose()


def test_audit_ids_are_backfilled_owner_only_and_claimed_only_by_the_trigger(env):
    """audit_log_ids: Altbestand steht nach der Migration drin, Zeilen der
    Eigentuemerin werden mit vergeben, die App-Rolle hat keine Rechte auf die
    Tabelle und kann pz_audit_claim_id nicht direkt (ausserhalb des Triggers)
    aufrufen - sonst belegte sie fremde ids vorab."""
    from app.models import TimeEntryAuditLog
    url, engine, app_url, role = env
    owner = sessionmaker(bind=engine)()
    try:
        owner.execute(text("SET LOCAL app.is_superadmin = 'true'"))
        assert owner.execute(text("SELECT count(*) FROM audit_log_ids WHERE id = :i"),
                             {"i": LEGACY}).scalar() == 1
        mine = TimeEntryAuditLog(tenant_id=uuid.UUID(TENANT), user_id=uuid.UUID(ADM),
                                 changed_by=uuid.UUID(ADM), action="update", source="manual")
        owner.add(mine)
        owner.flush()
        assert owner.execute(text("SELECT tenant_id FROM audit_log_ids WHERE id = :i"),
                             {"i": str(mine.id)}).scalar() == uuid.UUID(TENANT)
        owner.commit()
    finally:
        owner.close()
    eng, s = _app_session(app_url)
    try:
        s.commit()
        _expect_denied(s, "SELECT count(*) FROM audit_log_ids")
        _expect_denied(s, "DELETE FROM audit_log_ids")
        msg = _expect_denied(s, "SELECT pz_audit_claim_id(gen_random_uuid(), :t)", {"t": TENANT})
        assert "nur ueber den Protokoll-Trigger" in msg
        with engine.connect() as conn:
            privs = {p for (p,) in conn.execute(text(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE table_name = 'audit_log_ids' AND grantee = :r"), {"r": role})}
        assert privs == set()
        _insert_hashed(s)  # der normale Weg vergibt die id selbst
    finally:
        s.close()
        eng.dispose()


def test_app_role_rows_need_a_present_created_at(env):
    """created_at steht in der Pruefsumme; eine kopierte alte Zeile (neue id,
    alter Zeitpunkt) wird schon beim Einfuegen abgelehnt."""
    from datetime import datetime, timedelta, timezone
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        s.commit()  # Mandanten-Kontext festschreiben (der Rollback nimmt ihn sonst zurueck)
        old = datetime.now(timezone.utc) - timedelta(days=1)
        msg = _expect_denied(s, (
            "INSERT INTO time_entry_audit_logs (id, tenant_id, user_id, changed_by, action, source, "
            "created_at, row_hash, hash_version) VALUES (gen_random_uuid(), :t, :u, :a, 'update', "
            "'manual', :c, 'x', 3)"), {"t": TENANT, "u": EMP, "a": ADM, "c": old})
        assert "Gegenwart" in msg
        _insert_hashed(s)  # normaler Weg (created_at beim Flush) geht
    finally:
        s.close()
        eng.dispose()


def test_set_head_reanchor_ignores_a_marker_from_an_earlier_transaction(env):
    """Zweite Verteidigungslinie: das Zuruecksetzen gilt nur mit einem Vermerk
    aus derselben Transaktion — ein alter loser Vermerk (hier von der
    Eigentuemerin mit altem Zeitpunkt angelegt) reicht nicht."""
    from datetime import datetime, timedelta, timezone
    from app.models import TimeEntryAuditLog
    from app.services import audit_chain_service as acs
    url, engine, app_url, role = env
    eng, s = _app_session(app_url)
    try:
        for _ in range(3):
            _insert_hashed(s)
        acs.seal_chain(s, uuid.UUID(TENANT))
        s.commit()
        seq, _h, _mac = _head_value(engine).split(":")
        seq = int(seq)
        top = s.execute(text("SELECT id FROM time_entry_audit_logs WHERE tenant_id = :t "
                             "AND chain_seq = :q"), {"t": TENANT, "q": seq}).scalar()
        prev_hash = s.execute(text("SELECT chain_hash FROM time_entry_audit_logs WHERE "
                                   "tenant_id = :t AND chain_seq = :q"),
                              {"t": TENANT, "q": seq - 1}).scalar()
        s.execute(text("SELECT pz_audit_delete(ARRAY[CAST(:i AS uuid)])"), {"i": str(top)})
        s.commit()
        owner = sessionmaker(bind=engine)()
        try:
            owner.execute(text("SET LOCAL app.is_superadmin = 'true'"))
            owner.add(TimeEntryAuditLog(
                tenant_id=uuid.UUID(TENANT), user_id=uuid.UUID(ADM), changed_by=uuid.UUID(ADM),
                action="audit_chain_reanchored", source="audit_reanchor", new_note="alt",
                created_at=datetime.now(timezone.utc) - timedelta(hours=2)))
            owner.commit()
        finally:
            owner.close()
        msg = _expect_denied(s, "SELECT pz_audit_set_head(:t, :v, true)",
                             {"t": TENANT, "v": f"{seq - 1}:{prev_hash}:00"})
        assert "zurueck" in msg
    finally:
        s.close()
        eng.dispose()


# ── Wiederherstellung (Review-Runde 4): Funktionsabgleich gegen echtes PG ──

def _server_module():
    import importlib.util
    path = BACKEND.parent / "praxiszeit-server.py"
    if not path.exists():
        pytest.skip("praxiszeit-server.py fehlt (nur Backend gemountet)")
    spec = importlib.util.spec_from_file_location("praxiszeit_server_076", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restore_routine_check_matches_a_real_migrated_database(env):
    """Der Katalog einer frisch migrierten Datenbank (Stand 076) entspricht
    genau dem, was ``expected_db_routines`` aus den Migrationen liest -
    inklusive der Speicherform von ``SET search_path`` (proconfig). Eine
    veraenderte Funktion, eine fremde Funktion und eine Sicht fallen auf."""
    import json
    srv = _server_module()
    url, engine, app_url, role = env
    expected = srv.expected_db_routines(BACKEND / "alembic" / "versions", HEAD_REV)

    def problems():
        with engine.connect() as conn:
            raw = conn.exec_driver_sql(srv._ROUTINE_CATALOG_SQL.replace("%", "%%")).scalar()
        found = raw if isinstance(raw, dict) else json.loads(raw)
        return srv.check_restored_routines(found, *expected)

    assert problems() == []
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION pz_audit_tenant_ok(p_tenant uuid) RETURNS boolean "
            "LANGUAGE sql STABLE AS $$ SELECT true $$")
        conn.exec_driver_sql("CREATE FUNCTION boese() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$")
        conn.exec_driver_sql("CREATE VIEW v076 AS SELECT 1 AS x")
    got = problems()
    assert "Funktion public.pz_audit_tenant_ok (Inhalt weicht von der Migration ab)" in got
    assert "Funktion public.boese (legt keine Migration an)" in got
    assert "Sicht public.v076" in got

