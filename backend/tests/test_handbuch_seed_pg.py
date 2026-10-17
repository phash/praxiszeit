"""Handbuch-Seed (``create_handbuch_testdata.py``) gegen **echtes PostgreSQL mit RLS**.

Warum diese Datei existiert (Gesamtreview 1.20, B9)
===================================================
Der Seed meldete „1 Change Requests erstellt", obwohl er zwei Korrekturanträge
anlegen soll (Maria: offen, Thomas: abgelehnt). Ursache: ``_insert_change_request``
schrieb an SQLAlchemy vorbei über die rohe DBAPI-Verbindung und rief dort
``commit()`` auf. Der Mandantenkontext steht aber per ``SET LOCAL`` nur in der
laufenden Transaktion; ``app.database._restore_tenant_context`` setzt ihn nach
einem Commit über das ``after_begin``-Ereignis der Session neu — ein Commit an
der Session vorbei löst dieses Ereignis nie aus. Die nächste Abfrage (Thomas'
Zeiteintrag) lief damit ohne ``app.is_superadmin``, RLS lieferte 0 Zeilen, der
zweite Antrag fiel still weg.

SQLite kennt weder RLS noch ``SET LOCAL`` — der Fehler ist nur hier sichtbar.
Die App-Verbindung muss die RLS-gebundene Rolle sein (``praxiszeit_app``); als
Eigentümer oder Superuser greift RLS nicht, der Test prüft das als Voraussetzung.

Wo dieser Test läuft
====================
Nur mit erreichbarem PostgreSQL (sonst modulweiter Skip). Eingehängt in
``scripts/local-ci.sh`` Schritt 2 und in den PostgreSQL-Schritt von
``.github/workflows/cross-tenant-ci.yml``. Alle Zeilen hängen an einem eigenen
Mandanten mit fester UUID und werden vorher und nachher restlos entfernt.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

APP_DB_URL = os.environ.get("APP_DB_URL") or os.environ.get("DATABASE_URL") or ""
ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS") or ""
if not (APP_DB_URL.startswith("postgresql") and ADMIN_DB_URL.startswith("postgresql")):
    pytest.skip(
        "test_handbuch_seed_pg.py braucht PostgreSQL: APP_DB_URL (RLS-gebundene "
        "App-Rolle) und ADMIN_DB_URL bzw. DATABASE_URL_MIGRATIONS.",
        allow_module_level=True,
    )

from app.database import SessionLocal, set_superadmin_context  # noqa: E402
from app.models import ChangeRequest, User  # noqa: E402
from app.models.change_request import ChangeRequestStatus, ChangeRequestType  # noqa: E402

TENANT_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000001")
MARIA_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000101")
THOMAS_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000102")
ADMIN_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000103")
MARIA_ENTRY_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000201")
THOMAS_ENTRY_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000202")
# Fremder Mandant für die Gegenprobe der Mandantenfilter (Superadmin-Kontext).
FOREIGN_TENANT_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000002")
FOREIGN_ADMIN_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000301")
FOREIGN_MARIA_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000302")

SEED_PATH = Path(__file__).resolve().parent.parent / "create_handbuch_testdata.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("handbuch_seed_under_test", SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cleanup(conn):
    # Abhängige Zeilen BEIDER Mandanten zuerst: die Gegenproben hängen Zeilen des
    # fremden Mandanten an Konten des Zielmandanten (user_id ohne ON DELETE).
    tids = {"a": str(TENANT_ID), "b": str(FOREIGN_TENANT_ID)}
    for table in ("change_requests", "time_entries", "absences", "public_holidays", "users"):
        conn.execute(text(f"DELETE FROM {table} WHERE tenant_id IN (:a, :b)"), tids)
    conn.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), tids)


@pytest.fixture(scope="module")
def admin_engine():
    eng = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def app_engine():
    eng = create_engine(APP_DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def seeded(admin_engine):
    """Mandant mit Maria, Thomas und einer Verwalterin samt den beiden
    Zeiteinträgen, an denen der Seed die Anträge festmacht."""
    with admin_engine.connect() as conn:
        _cleanup(conn)
        conn.execute(text(
            "INSERT INTO tenants (id, name, slug, is_active, mode) "
            "VALUES (:id, 'B9 Seed-Test', 'b9-seed-test', true, 'multi')"
        ), {"id": str(TENANT_ID)})
        insert_user = text("""
            INSERT INTO users (id, tenant_id, username, email, password_hash,
                               first_name, last_name, role, weekly_hours,
                               vacation_days, work_days_per_week, is_active)
            VALUES (:id, :tid, :username, :email, 'not-a-real-hash',
                    :first, :last, :role, 40, 30, 5, true)
        """)
        for uid, username, first, last, role in (
            (MARIA_ID, "maria.hoffmann", "Maria", "Hoffmann", "EMPLOYEE"),
            (THOMAS_ID, "thomas.bauer", "Thomas", "Bauer", "EMPLOYEE"),
            (ADMIN_ID, "admin", "Andreas", "Werner", "ADMIN"),
        ):
            conn.execute(insert_user, {
                "id": str(uid), "tid": str(TENANT_ID), "username": username,
                "email": f"{username}@b9-seed.invalid", "first": first, "last": last,
                "role": role,
            })
        insert_entry = text("""
            INSERT INTO time_entries (id, tenant_id, user_id, date, start_time, end_time, break_minutes)
            VALUES (:id, :tid, :uid, :dt, :st, :et, :brk)
        """)
        conn.execute(insert_entry, {"id": str(MARIA_ENTRY_ID), "tid": str(TENANT_ID),
                                    "uid": str(MARIA_ID), "dt": "2026-02-10",
                                    "st": "08:15", "et": "16:45", "brk": 45})
        conn.execute(insert_entry, {"id": str(THOMAS_ENTRY_ID), "tid": str(TENANT_ID),
                                    "uid": str(THOMAS_ID), "dt": "2026-01-15",
                                    "st": "07:30", "et": "16:30", "brk": 45})
    yield
    with admin_engine.connect() as conn:
        _cleanup(conn)


def test_app_connection_is_bound_by_rls(seeded, app_engine):
    """Voraussetzung: ohne Kontext sieht die App-Verbindung die Zeilen NICHT.
    Sonst bewiese der eigentliche Test nichts (Eigentümer/Superuser umgehen RLS)."""
    with app_engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM time_entries WHERE tenant_id = :tid"),
                         {"tid": str(TENANT_ID)}).scalar()
    assert n == 0, "APP_DB_URL umgeht RLS — als praxiszeit_app verbinden"


def test_seed_creates_both_change_requests(seeded, app_engine, monkeypatch, capsys):
    seed = _load_seed()
    monkeypatch.setattr(seed, "TENANT_ID", str(TENANT_ID))

    db = SessionLocal(bind=app_engine)
    try:
        set_superadmin_context(db)
        users = db.query(User).filter(User.tenant_id == TENANT_ID).all()
        reviewer = next(u for u in users if u.username == "admin")
        seed.create_change_requests(db, users, reviewer=reviewer)
    finally:
        db.close()

    assert "2 Change Requests erstellt" in capsys.readouterr().out

    check = SessionLocal(bind=app_engine)
    try:
        set_superadmin_context(check)
        crs = {
            cr.user_id: cr
            for cr in check.query(ChangeRequest).filter(ChangeRequest.tenant_id == TENANT_ID)
        }
    finally:
        check.close()

    assert set(crs) == {MARIA_ID, THOMAS_ID}

    maria = crs[MARIA_ID]
    assert maria.status == ChangeRequestStatus.PENDING
    assert maria.request_type == ChangeRequestType.UPDATE
    assert maria.time_entry_id == MARIA_ENTRY_ID
    # Vorher-Bild wie bei einem echten Antrag (change_requests.create_change_request):
    # ohne Datum zeigt die Antragsliste der Screenshots keine Datumszeile.
    assert str(maria.original_date) == str(maria.proposed_date) == "2026-02-10"
    assert (str(maria.original_start_time), str(maria.original_end_time),
            maria.original_break_minutes) == ("08:15:00", "16:45:00", 45)
    assert (str(maria.proposed_start_time), str(maria.proposed_end_time),
            maria.proposed_break_minutes) == ("08:00:00", "16:45:00", 45)
    assert maria.reviewed_by is None and maria.reviewed_at is None

    thomas = crs[THOMAS_ID]
    assert thomas.status == ChangeRequestStatus.REJECTED
    assert thomas.time_entry_id == THOMAS_ENTRY_ID
    assert str(thomas.original_date) == str(thomas.proposed_date) == "2026-01-15"
    assert thomas.rejection_reason
    # Abgelehnt heißt: von jemandem, zu einem Zeitpunkt (wie review_change_request).
    assert thomas.reviewed_by == ADMIN_ID
    assert thomas.reviewed_at is not None


# ── Mandantenfilter im Superadmin-Kontext ───────────────────────────────────
#
# Der Seed läuft unter ``set_superadmin_context`` — RLS greift dort nicht, jede
# Abfrage muss den Mandanten selbst filtern (CLAUDE.md, Security-Review
# 2026-07-25). Ohne Filter traf der Seed in einer Datenbank mit mehreren
# Mandanten (SaaS-Entwicklung, E2E-Signups) die Zeilen eines FREMDEN Mandanten:
# das Admin-Konto eines anderen Mandanten bekam Name, E-Mail und Passwort der
# Musterpraxis, eine gleichnamige fremde Mitarbeiterin wurde als „existiert
# bereits" übernommen und bekam die Demo-Daten, und fremde Feiertage strichen
# Arbeitstage aus dem Demo-Zeitraum.


@pytest.fixture
def foreign_tenant(admin_engine):
    """Zielmandant ohne Konten, fremder Mandant mit ``admin`` und
    ``maria.hoffmann`` — dazu je ein Feiertag im Demo-Zeitraum."""
    with admin_engine.connect() as conn:
        _cleanup(conn)
        for tid, slug in ((TENANT_ID, "b9-seed-test"), (FOREIGN_TENANT_ID, "b9-seed-fremd")):
            conn.execute(text(
                "INSERT INTO tenants (id, name, slug, is_active, mode) "
                "VALUES (:id, :slug, :slug, true, 'multi')"
            ), {"id": str(tid), "slug": slug})
        insert_user = text("""
            INSERT INTO users (id, tenant_id, username, email, password_hash,
                               first_name, last_name, role, weekly_hours,
                               vacation_days, work_days_per_week, is_active)
            VALUES (:id, :tid, :username, :email, 'fremder-hash',
                    'Fremd', 'Konto', :role, 40, 30, 5, true)
        """)
        for uid, username, role in ((FOREIGN_ADMIN_ID, "admin", "ADMIN"),
                                    (FOREIGN_MARIA_ID, "maria.hoffmann", "EMPLOYEE")):
            conn.execute(insert_user, {"id": str(uid), "tid": str(FOREIGN_TENANT_ID),
                                       "username": username,
                                       "email": f"{username}@b9-fremd.invalid", "role": role})
        insert_holiday = text(
            "INSERT INTO public_holidays (id, tenant_id, date, name, year) "
            "VALUES (:id, :tid, :dt, :name, 2026)"
        )
        conn.execute(insert_holiday, {"id": str(uuid.uuid4()), "tid": str(TENANT_ID),
                                      "dt": "2026-01-06", "name": "Heilige Drei Könige"})
        conn.execute(insert_holiday, {"id": str(uuid.uuid4()), "tid": str(FOREIGN_TENANT_ID),
                                      "dt": "2026-01-20", "name": "Fremder Feiertag"})
    yield
    with admin_engine.connect() as conn:
        _cleanup(conn)


def _foreign_user(admin_engine, uid):
    with admin_engine.connect() as conn:
        return conn.execute(text(
            "SELECT first_name, email, password_hash, weekly_hours FROM users WHERE id = :id"
        ), {"id": str(uid)}).one()


def _seed_session(app_engine, seed, monkeypatch):
    monkeypatch.setattr(seed, "TENANT_ID", str(TENANT_ID))
    db = SessionLocal(bind=app_engine)
    set_superadmin_context(db)
    return db


def test_admin_update_stays_in_own_tenant(foreign_tenant, admin_engine, app_engine,
                                          monkeypatch, capsys):
    seed = _load_seed()
    db = _seed_session(app_engine, seed, monkeypatch)
    try:
        seed.update_admin_password(db)
    finally:
        db.close()
    assert "Admin-User nicht gefunden" in capsys.readouterr().out
    first_name, email, password_hash, _ = _foreign_user(admin_engine, FOREIGN_ADMIN_ID)
    assert (first_name, email, password_hash) == ("Fremd", "admin@b9-fremd.invalid", "fremder-hash")


def test_holidays_come_from_own_tenant(foreign_tenant, app_engine, monkeypatch):
    from datetime import date

    seed = _load_seed()
    db = _seed_session(app_engine, seed, monkeypatch)
    try:
        assert seed.get_holiday_dates(db) == {date(2026, 1, 6)}
    finally:
        db.close()


def test_employees_are_created_in_own_tenant(foreign_tenant, admin_engine, app_engine,
                                             monkeypatch):
    seed = _load_seed()
    db = _seed_session(app_engine, seed, monkeypatch)
    try:
        users = seed.create_employees(db)
        assert {u.tenant_id for u in users} == {TENANT_ID}
        assert len(users) == len(seed.EMPLOYEES)
    finally:
        db.close()
    # Die gleichnamige fremde Mitarbeiterin bleibt unberührt.
    first_name, email, _, weekly_hours = _foreign_user(admin_engine, FOREIGN_MARIA_ID)
    assert (first_name, email, float(weekly_hours)) == ("Fremd", "maria.hoffmann@b9-fremd.invalid", 40.0)


# ── Zeilen mit falsch gesetzter tenant_id ───────────────────────────────────
#
# Gesamtreview 1.20 (B9, Nachzug): auch die Abfragen, die schon über ``user_id``
# eingeengt sind, filtern den Mandanten selbst — im Superadmin-Kontext ist das
# nicht optional (CLAUDE.md). Gegenprobe: eine Zeile des FREMDEN Mandanten, die
# (falsch abgelegt) an einem Konto des Zielmandanten hängt. Ohne Filter strich
# eine solche Abwesenheit einen Demo-Arbeitstag, und ein solcher Zeiteintrag
# bekam den Korrekturantrag der Musterpraxis.

OWN_MARIA_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000111")
OWN_THOMAS_ID = uuid.UUID("b9b90000-0000-4000-8000-000000000112")


@pytest.fixture
def misfiled_rows(foreign_tenant, admin_engine):
    """Maria und Thomas im Zielmandanten; im fremden Mandanten eine Abwesenheit
    (Mi 07.01.2026) und zwei Zeiteinträge an genau den Tagen, an denen der Seed
    die Korrekturanträge festmacht — alle mit der user_id der eigenen Konten."""
    with admin_engine.connect() as conn:
        insert_user = text("""
            INSERT INTO users (id, tenant_id, username, email, password_hash,
                               first_name, last_name, role, weekly_hours,
                               vacation_days, work_days_per_week, is_active)
            VALUES (:id, :tid, :username, :email, 'not-a-real-hash',
                    :first, :last, 'EMPLOYEE', 40, 30, 5, true)
        """)
        for uid, username, first, last in ((OWN_MARIA_ID, "maria.hoffmann", "Maria", "Hoffmann"),
                                           (OWN_THOMAS_ID, "thomas.bauer", "Thomas", "Bauer")):
            conn.execute(insert_user, {"id": str(uid), "tid": str(TENANT_ID), "username": username,
                                       "email": f"{username}@b9-seed.invalid",
                                       "first": first, "last": last})
        conn.execute(text("""
            INSERT INTO absences (id, tenant_id, user_id, date, type, hours)
            VALUES (:id, :tid, :uid, '2026-01-07', 'VACATION', 8)
        """), {"id": str(uuid.uuid4()), "tid": str(FOREIGN_TENANT_ID), "uid": str(OWN_MARIA_ID)})
        insert_entry = text("""
            INSERT INTO time_entries (id, tenant_id, user_id, date, start_time, end_time, break_minutes)
            VALUES (:id, :tid, :uid, :dt, '08:15', '16:45', 45)
        """)
        for uid, dt in ((OWN_MARIA_ID, "2026-02-10"), (OWN_THOMAS_ID, "2026-01-15")):
            conn.execute(insert_entry, {"id": str(uuid.uuid4()), "tid": str(FOREIGN_TENANT_ID),
                                        "uid": str(uid), "dt": dt})
    yield


def _own_users(db):
    return db.query(User).filter(User.tenant_id == TENANT_ID).order_by(User.username).all()


def test_foreign_absence_does_not_skip_own_workday(misfiled_rows, app_engine, monkeypatch):
    from datetime import date

    from app.models import TimeEntry

    seed = _load_seed()
    db = _seed_session(app_engine, seed, monkeypatch)
    try:
        maria = next(u for u in _own_users(db) if u.id == OWN_MARIA_ID)
        seed.create_time_entries_for_user(db, maria, set())
        own_days = {
            e.date for e in db.query(TimeEntry).filter(
                TimeEntry.tenant_id == TENANT_ID, TimeEntry.user_id == OWN_MARIA_ID,
            )
        }
    finally:
        db.close()
    assert date(2026, 1, 7) in own_days


def test_change_requests_ignore_foreign_entries(misfiled_rows, app_engine, monkeypatch, capsys):
    seed = _load_seed()
    db = _seed_session(app_engine, seed, monkeypatch)
    try:
        seed.create_change_requests(db, _own_users(db))
        n = db.query(ChangeRequest).filter(
            ChangeRequest.user_id.in_([OWN_MARIA_ID, OWN_THOMAS_ID]),
        ).count()
    finally:
        db.close()
    assert "0 Change Requests erstellt" in capsys.readouterr().out
    assert n == 0
