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
from datetime import date, time, timedelta
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
    # Reihenfolge nach FK-Abhängigkeit: Abwesenheiten vor Betriebsferien und
    # Abwesenheitsgründen, alles vor den Konten (created_by/user_id).
    # Schichtplan (Einteilungen/Schichten vor dem Plan, Einweisungen vor den Arbeitsplätzen;
    # shift_plans.created_by verweist auf die Verwalterin)
    for table in ("shift_assignments", "shift_slots", "shift_plans", "workstation_qualifications",
                  "workstations",
                  "change_requests", "vacation_requests", "time_entries", "absences",
                  "company_closures", "absence_reasons", "reduced_days",
                  "working_hours_changes", "system_settings", "public_holidays", "users"):
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
            (MARIA_ID, "maria", "Maria", "Hoffmann", "EMPLOYEE"),
            (THOMAS_ID, "thomas", "Thomas", "Bauer", "EMPLOYEE"),
            (ADMIN_ID, "admin", "Andrea", "Werner", "ADMIN"),
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
        seed.create_change_requests(db, users, date(2026, 2, 11), reviewer=reviewer)
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
                                    (FOREIGN_MARIA_ID, "maria", "EMPLOYEE")):
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
    seed = _load_seed()
    db = _seed_session(app_engine, seed, monkeypatch)
    try:
        assert seed.get_holiday_dates(db, date(2026, 1, 1), date(2026, 2, 27)) == {date(2026, 1, 6)}
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
        assert sorted(u.username for u in users) == ["julia", "maria", "petra", "sarah", "thomas"]
    finally:
        db.close()
    # Die gleichnamige fremde Mitarbeiterin bleibt unberührt.
    first_name, email, _, weekly_hours = _foreign_user(admin_engine, FOREIGN_MARIA_ID)
    assert (first_name, email, float(weekly_hours)) == ("Fremd", "maria@b9-fremd.invalid", 40.0)


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
        for uid, username, first, last in ((OWN_MARIA_ID, "maria", "Maria", "Hoffmann"),
                                           (OWN_THOMAS_ID, "thomas", "Thomas", "Bauer")):
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
    from app.models import TimeEntry

    seed = _load_seed()
    db = _seed_session(app_engine, seed, monkeypatch)
    try:
        maria = next(u for u in _own_users(db) if u.id == OWN_MARIA_ID)
        seed.create_time_entries_for_user(db, maria, set(), date(2026, 1, 5), date(2026, 1, 9))
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
        seed.create_change_requests(db, _own_users(db), date(2026, 2, 11))
        n = db.query(ChangeRequest).filter(
            ChangeRequest.user_id.in_([OWN_MARIA_ID, OWN_THOMAS_ID]),
        ).count()
    finally:
        db.close()
    assert "0 Change Requests erstellt" in capsys.readouterr().out
    assert n == 0


# ── Demodaten relativ zum Stichtag (Handbuch grafisch, Task 4) ─────────────

STICHTAG = date(2026, 3, 11)  # Mittwoch
SEED_HOLIDAY = date(2026, 3, 2)  # Montag, nur in diesem Testmandanten Feiertag


def test_default_stichtag_is_wednesday():
    seed = _load_seed()
    assert seed.default_stichtag(date(2026, 11, 10)) == date(2026, 10, 28)
    # Feiertag am Mittwoch -> naechster Werktag (Donnerstag)
    assert seed.default_stichtag(date(2026, 11, 10), {date(2026, 10, 28)}) == date(2026, 10, 29)


@pytest.fixture
def full_tenant(admin_engine):
    """Mandant mit Verwalterin ``admin`` (wie nach dem Bootstrap) und einem
    Feiertag im Demo-Zeitraum."""
    with admin_engine.connect() as conn:
        _cleanup(conn)
        conn.execute(text(
            "INSERT INTO tenants (id, name, slug, is_active, mode) "
            "VALUES (:id, 'B9 Seed-Test', 'b9-seed-test', true, 'multi')"
        ), {"id": str(TENANT_ID)})
        conn.execute(text("""
            INSERT INTO users (id, tenant_id, username, email, password_hash,
                               first_name, last_name, role, weekly_hours,
                               vacation_days, work_days_per_week, is_active)
            VALUES (:id, :tid, 'admin', 'admin@b9-seed.invalid', 'x', 'Andrea', 'Werner',
                    'ADMIN', 40, 30, 5, true)
        """), {"id": str(ADMIN_ID), "tid": str(TENANT_ID)})
        conn.execute(text(
            "INSERT INTO public_holidays (id, tenant_id, date, name, year) "
            "VALUES (:id, :tid, :dt, 'Testfeiertag', 2026)"
        ), {"id": str(uuid.uuid4()), "tid": str(TENANT_ID), "dt": str(SEED_HOLIDAY)})
    yield
    with admin_engine.connect() as conn:
        _cleanup(conn)


def _run_seed(app_engine, seed, monkeypatch, stichtag=STICHTAG):
    monkeypatch.setattr(seed, "TENANT_ID", str(TENANT_ID))
    db = SessionLocal(bind=app_engine)
    try:
        set_superadmin_context(db)
        seed.seed_all(db, stichtag)
    finally:
        db.close()


def _read(app_engine, fn):
    db = SessionLocal(bind=app_engine)
    try:
        set_superadmin_context(db)
        return fn(db)
    finally:
        db.close()


def test_seed_relative_to_stichtag(full_tenant, app_engine, monkeypatch):
    from app.models import Absence, TimeEntry
    from app.models.company_closure import CompanyClosure
    from app.models.vacation_request import VacationRequest

    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)

    def collect(db):
        users = {u.username: u for u in db.query(User).filter(User.tenant_id == TENANT_ID)}
        entries = db.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID).all()
        maria = users["maria"]
        return {
            "usernames": set(users),
            "maria_dates": {e.date for e in entries if e.user_id == maria.id},
            "all_dates": {e.date for e in entries},
            "open": [e.date for e in entries if e.user_id == maria.id and e.end_time is None],
            "open_start": [e.start_time for e in entries if e.user_id == maria.id and e.end_time is None],
            "first_date": min(e.date for e in entries),
            "last_date": max(e.date for e in entries),
            "vr": [(v.user_id, v.status, v.date, v.end_date) for v in
                   db.query(VacationRequest).filter(VacationRequest.tenant_id == TENANT_ID)],
            "thomas_id": users["thomas"].id,
            "closures": [(c.start_date, c.end_date) for c in
                         db.query(CompanyClosure).filter(CompanyClosure.tenant_id == TENANT_ID)],
            "absence_dates": {(a.user_id, a.date) for a in
                              db.query(Absence).filter(Absence.tenant_id == TENANT_ID)},
            "entry_keys": {(e.user_id, e.date) for e in entries},
        }

    r = _read(app_engine, collect)
    assert r["usernames"] == {"admin", "maria", "sarah", "thomas", "petra", "julia"}
    assert date(2026, 3, 10) in r["maria_dates"]
    assert r["open"] == [STICHTAG] and r["open_start"] == [time(7, 45)]
    # YTD-Realismus: Daten ab 1. Januar des Stichtag-Jahres, nie davor
    assert date(2026, 1, 1) <= r["first_date"] < date(2026, 2, 1) and r["last_date"] <= STICHTAG
    assert not [d for d in r["all_dates"] if d.weekday() >= 5], "Eintrag am Wochenende"
    assert SEED_HOLIDAY not in r["all_dates"], "Eintrag am Feiertag"
    # kein Eintrag am Tag einer Abwesenheit derselben Person
    assert not (r["absence_dates"] & r["entry_keys"])
    pending = [v for v in r["vr"] if v[1] == "pending"]
    assert pending and all(v[0] == r["thomas_id"] and v[2] > STICHTAG for v in pending)
    assert r["closures"] and all(c[0] > STICHTAG for c in r["closures"])


def test_seed_creates_new_feature_objects(full_tenant, app_engine, monkeypatch):
    from datetime import timedelta
    from decimal import Decimal

    from app.models import Absence, TimeEntry, WorkingHoursChange
    from app.models.absence import AbsenceReason, AbsenceType
    from app.models.reduced_day import ReducedDay
    from app.models.system_setting import SystemSetting

    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)

    def collect(db):
        users = {u.username: u for u in db.query(User).filter(User.tenant_id == TENANT_ID)}
        by_id = {u.id: u.username for u in users.values()}
        month_start = STICHTAG.replace(day=1)
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
        return {
            "by_id": by_id,
            "reduced": [(r.date, r.max_hours) for r in db.query(ReducedDay).filter(ReducedDay.tenant_id == TENANT_ID)],
            "settings": {s.key: s.value for s in db.query(SystemSetting).filter(SystemSetting.tenant_id == TENANT_ID)},
            "reasons": [(r.name, r.base_behavior) for r in db.query(AbsenceReason).filter(AbsenceReason.tenant_id == TENANT_ID)],
            "whc": sorted((by_id[w.user_id], w.effective_from, float(w.vacation_days), float(w.weekly_hours), w.blocks is not None)
                          for w in db.query(WorkingHoursChange).filter(WorkingHoursChange.tenant_id == TENANT_ID)),
            "absences": [(by_id[a.user_id], a.type, a.date, float(a.hours), a.reason_id is not None, a.closure_id is not None)
                         for a in db.query(Absence).filter(Absence.tenant_id == TENANT_ID)],
            "waiver": [(by_id[e.user_id], e.date, float(e.net_hours), e.break_minutes)
                       for e in db.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID,
                                                           TimeEntry.break_waiver_reason.isnot(None))],
            "crs": sorted((by_id[c.user_id], c.status.value if hasattr(c.status, "value") else c.status)
                          for c in db.query(ChangeRequest).filter(ChangeRequest.tenant_id == TENANT_ID)),
            "month_start": month_start, "prev_month_start": prev_month_start,
            "contract": {k: (float(u.weekly_hours), u.work_days_per_week, bool(u.milog_working_time_account), float(u.vacation_days))
                         for k, u in users.items()},
        }

    r = _read(app_engine, collect)
    assert len(r["reduced"]) == 1 and r["reduced"][0][0] < STICHTAG and r["reduced"][0][1] == Decimal("4.00")
    assert r["settings"]["special_day_dec24_mode"] == "half_day"
    assert r["settings"]["special_day_dec31_mode"] == "half_day"
    assert ("Fortbildung extern", "worked") in r["reasons"]
    # Petra: Anspruch ab Monatsanfang geaendert (Vertragsverlauf), Sarah: Aenderung im Vormonat
    petra = [w for w in r["whc"] if w[0] == "petra"]
    assert len(petra) == 2 and petra[-1][1] == r["month_start"] and petra[0][2] != petra[-1][2]
    sarah = [w for w in r["whc"] if w[0] == "sarah"]
    assert len(sarah) == 2 and all(w[4] for w in sarah) and sarah[-1][1].month == r["prev_month_start"].month
    ab = r["absences"]
    maria_vac = [a for a in ab if a[0] == "maria" and a[1] == AbsenceType.VACATION and not a[5]]
    assert len(maria_vac) == 3 and all(a[2] < STICHTAG for a in maria_vac) and all(a[3] == 8.0 for a in maria_vac)
    assert len([a for a in ab if a[0] == "sarah" and a[1] == AbsenceType.SICK]) == 2
    assert any(a[0] == "thomas" and a[1] == AbsenceType.TRAINING and a[4] for a in ab)  # eigener Grund
    closure_days = [a for a in ab if a[5]]
    assert closure_days and all(a[2] > STICHTAG for a in closure_days)
    assert {a[0] for a in closure_days} == {"maria", "thomas", "sarah", "petra", "julia"}
    assert len(r["waiver"]) == 1 and r["waiver"][0][0] == "thomas"
    assert r["waiver"][0][2] == 6.5 and r["waiver"][0][3] == 0
    assert r["crs"] == [("maria", "pending"), ("thomas", "rejected")]
    c = r["contract"]
    assert c["maria"][:2] == (40.0, 5) and c["thomas"][0] == 38.5 and c["sarah"][0] == 25.0
    assert c["petra"][:2] == (20.0, 4) and c["julia"][:3] == (10.0, 2, True)
    assert c["maria"][3] == 30.0


def test_seed_contains_no_legacy_domains(full_tenant, app_engine, monkeypatch):
    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)
    emails = _read(app_engine, lambda db: [u.email for u in db.query(User).filter(User.tenant_id == TENANT_ID)])
    assert emails and not [e for e in emails if e.endswith("@praxis.de") or "example.de" in e]
    assert sorted(e for e in emails if "lindenplatz" in e) == sorted([
        "admin@praxis-lindenplatz.example", "maria.hoffmann@praxis-lindenplatz.example",
        "thomas.bauer@praxis-lindenplatz.example", "sarah.klein@praxis-lindenplatz.example",
        "petra.schulz@praxis-lindenplatz.example", "julia.meyer@praxis-lindenplatz.example"])


def test_seed_is_rerunnable(full_tenant, app_engine, monkeypatch):
    """Zweiter Lauf loescht die gleichnamigen Demo-Konten samt Daten und legt neu an."""
    from app.models import TimeEntry
    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)
    n1 = _read(app_engine, lambda db: db.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID).count())
    _run_seed(app_engine, seed, monkeypatch)
    n2 = _read(app_engine, lambda db: db.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID).count())
    assert n1 == n2 > 0
    from app.models.company_closure import CompanyClosure
    closures = _read(app_engine, lambda db: db.query(CompanyClosure).filter(
        CompanyClosure.tenant_id == TENANT_ID).count())
    assert closures == 1, "Wiederholung darf keine zweite Betriebsferien-Zeile hinterlassen"
    users = _read(app_engine, lambda db: db.query(User).filter(User.tenant_id == TENANT_ID).count())
    assert users == 6


def test_main_prints_stichtag_as_last_line(full_tenant, app_engine, monkeypatch, capsys):
    seed = _load_seed()
    monkeypatch.setattr(seed, "TENANT_ID", str(TENANT_ID))
    monkeypatch.setattr(seed, "SessionLocal", lambda: SessionLocal(bind=app_engine))
    seed.main(["--stichtag", "2026-03-11"])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert lines[-1] == "STICHTAG=2026-03-11"


def test_pick_run_skips_half_day_special_days():
    seed = _load_seed()
    # Mo-Mi 21.-23.12. ist frei, Mo-Mi 22.-24.12. enthaelt den 24.12. -> naechster Montag
    assert seed.pick_run(date(2026, 12, 21), 3, set()) == [date(2026, 12, 21), date(2026, 12, 22), date(2026, 12, 23)]
    assert seed.pick_run(date(2026, 12, 22), 3, set())[0] == date(2026, 12, 28)
    # 28.-30.12. ok, 31.12. (Do) nicht Teil einer Mo-Mi-Folge; Fuenferfolge ab 28.12. enthaelt ihn -> Januar
    assert seed.pick_run(date(2026, 12, 28), 5, set())[0] == date(2027, 1, 4)


def test_reduced_day_cap_applies_to_block_persona(full_tenant, app_engine, monkeypatch):
    from decimal import Decimal
    from app.models import TimeEntry
    from app.models.reduced_day import ReducedDay

    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)

    def collect(db):
        sarah = db.query(User).filter(User.tenant_id == TENANT_ID, User.username == "sarah").one()
        day = db.query(ReducedDay).filter(ReducedDay.tenant_id == TENANT_ID).one()
        rows = db.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID,
                                          TimeEntry.user_id == sarah.id, TimeEntry.date == day.date).all()
        return day.date, day.max_hours, sum(float(e.net_hours) for e in rows), len(rows)

    d, cap, net, n = _read(app_engine, collect)
    assert d.weekday() == 4 and cap == Decimal("4.00")  # Freitag: Block 08-13 (5 h) ueber der Obergrenze
    assert n >= 1 and net <= 4.0 + 1e-6


def test_maria_vacation_has_approved_request(full_tenant, app_engine, monkeypatch):
    from app.models.vacation_request import VacationRequest
    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)
    rows = _read(app_engine, lambda db: [(v.status, v.reviewed_by, v.date, v.end_date, v.created_at, v.reviewed_at)
                                        for v in db.query(VacationRequest).join(User, User.id == VacationRequest.user_id)
                                        .filter(VacationRequest.tenant_id == TENANT_ID, User.username == "maria")])
    assert len(rows) == 1 and rows[0][0] == "approved" and rows[0][1] == ADMIN_ID and rows[0][3] < STICHTAG
    # „Meine Anträge" zeigt „Gestellt: …": vor dem Urlaub gestellt, danach genehmigt
    created, reviewed = rows[0][4], rows[0][5]
    assert created.date() < rows[0][2] and created < reviewed and reviewed.date() < rows[0][2]


def test_seed_writes_every_setting_default_as_a_row(full_tenant, app_engine, monkeypatch):
    """Jeder Schluessel aus settingsRestore.ts (SETTING_DEFAULTS) steht als Zeile
    in system_settings; die Python-Kopie im Seed gleicht der TS-Quelle."""
    import re

    from app.models.system_setting import SystemSetting

    ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "handbuch" / "settingsRestore.ts"
    if not ts.exists():  # im Backend-Container ohne Frontend-Quellen
        pytest.skip("frontend/src/handbuch/settingsRestore.ts nicht erreichbar")
    block = re.search(r"SETTING_DEFAULTS[^{]*\{(.*?)\n\};", ts.read_text(encoding="utf-8"), re.S).group(1)
    ts_defaults = dict(re.findall(r"(\w+):\s*'([^']*)'", block))
    assert ts_defaults

    seed = _load_seed()
    assert seed.SETTING_DEFAULTS == ts_defaults
    _run_seed(app_engine, seed, monkeypatch)
    rows = _read(app_engine, lambda db: {s.key: s.value for s in
                                        db.query(SystemSetting).filter(SystemSetting.tenant_id == TENANT_ID)})
    overrides = {"special_day_dec24_mode": "half_day", "special_day_dec31_mode": "half_day",
                 "vacation_approval_required": "true"}
    for key, default in ts_defaults.items():
        assert rows[key] == overrides.get(key, default), key


def test_no_entry_of_the_stichtag_ends_after_capture_time(full_tenant, app_engine, monkeypatch):
    """Aufgenommen wird am Stichtag um 10:30: kein Eintrag dieses Tages endet
    später (sonst zeigen die Listen Zeiten aus der Zukunft). Maria und Sarah
    sind eingestempelt (offen), die übrigen noch nicht."""
    from app.models import TimeEntry
    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)

    def collect(db):
        names = {u.id: u.username for u in db.query(User).filter(User.tenant_id == TENANT_ID)}
        return [(names[e.user_id], e.start_time, e.end_time) for e in db.query(TimeEntry).filter(
            TimeEntry.tenant_id == TENANT_ID, TimeEntry.date == STICHTAG)]

    rows = _read(app_engine, collect)
    assert not [r for r in rows if r[2] is not None and r[2] > time(10, 30)]
    assert not [r for r in rows if r[1] > time(10, 30)], "Beginn nach der Aufnahmezeit"
    assert sorted((r[0], r[1]) for r in rows if r[2] is None) == [("maria", time(7, 45)), ("sarah", time(8, 0))]


def test_thomas_forgot_to_stamp_on_the_fourth_workday_before(full_tenant, app_engine, monkeypatch):
    """Aufnahme ``ma-vergangener-tag`` (Persona thomas) füllt {{werktag-4}}: an
    diesem Werktag hat Thomas weder Eintrag noch Abwesenheit (Einstempeln
    vergessen); die Tage davor und danach sind belegt. Maria hat dagegen keinen
    fehlenden Werktag (ihr Dashboard zeigt kein „Buchung fehlt“, R19).
    Spiegel von dates.ts::workdayBefore."""
    from app.models import Absence, PublicHoliday, TimeEntry
    seed = _load_seed()
    assert seed.workday_before(date(2026, 10, 28), 4) == date(2026, 10, 22)
    assert seed.workday_before(date(2026, 11, 2), 1) == date(2026, 10, 30)
    _run_seed(app_engine, seed, monkeypatch)
    day = seed.workday_before(STICHTAG, seed.THOMAS_FORGOTTEN_WORKDAY)

    def collect(db):
        users = {u.username: u for u in db.query(User).filter(User.tenant_id == TENANT_ID)}
        def booked(name):
            uid = users[name].id
            entries = {e.date for e in db.query(TimeEntry).filter(
                TimeEntry.tenant_id == TENANT_ID, TimeEntry.user_id == uid)}
            absences = {a.date for a in db.query(Absence).filter(
                Absence.tenant_id == TENANT_ID, Absence.user_id == uid)}
            return entries, absences
        holidays = {h.date for h in db.query(PublicHoliday).filter(PublicHoliday.tenant_id == TENANT_ID)}
        waiver = [e.date for e in db.query(TimeEntry).filter(
            TimeEntry.tenant_id == TENANT_ID, TimeEntry.user_id == users["thomas"].id,
            TimeEntry.break_waiver_reason.isnot(None))]
        return booked("thomas"), booked("maria"), holidays, waiver

    (t_entries, t_abs), (m_entries, m_abs), holidays, waiver = _read(app_engine, collect)
    assert day not in t_entries and day not in t_abs
    assert seed.workday_before(STICHTAG, 3) in t_entries and seed.workday_before(STICHTAG, 5) in t_entries
    assert len(waiver) == 1 and waiver[0] != day  # §4-Befund bleibt erhalten
    # Maria: jeder vergangene Werktag im Stichtagsmonat ist belegt
    d = STICHTAG.replace(day=1)
    while d < STICHTAG:
        if d.weekday() < 5 and d not in holidays:
            assert d in m_entries or d in m_abs, f"Maria ohne Buchung am {d}"
        d += timedelta(days=1)


def test_seed_creates_shift_plan_visible_to_employees(full_tenant, app_engine, monkeypatch):
    """Aufnahmen ``ma-schichtplan``/``ma-einteilung-heute``: ein heute gültiger
    Plan, den Mitarbeitende sehen (``is_plan_visible_to``), Maria am Stichtag
    eingeteilt (mit »-Hinweis), Einweisungen zu jeder Einteilung. Die Planung
    schreibt nichts ins Rechenmodell; ein zweiter Lauf hinterlässt genau einen Plan."""
    from app.models import ShiftAssignment, ShiftPlan, ShiftSlot, TimeEntry, Workstation, WorkstationQualification
    from app.services.shift_planning_service import is_plan_visible_to
    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)
    entries_before = _read(app_engine, lambda db: db.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID).count())
    _run_seed(app_engine, seed, monkeypatch)

    def collect(db):
        names = {u.id: u.username for u in db.query(User).filter(User.tenant_id == TENANT_ID)}
        plans = db.query(ShiftPlan).filter(ShiftPlan.tenant_id == TENANT_ID).all()
        ws = {w.id: w.name for w in db.query(Workstation).filter(Workstation.tenant_id == TENANT_ID)}
        slots = db.query(ShiftSlot).filter(ShiftSlot.tenant_id == TENANT_ID).all()
        by_slot = {s.id: s for s in slots}
        assigns = [(names[a.user_id], by_slot[a.shift_slot_id]) for a in
                   db.query(ShiftAssignment).filter(ShiftAssignment.tenant_id == TENANT_ID)]
        quals = {(names[q.user_id], ws[q.workstation_id]) for q in
                 db.query(WorkstationQualification).filter(WorkstationQualification.tenant_id == TENANT_ID)}
        return {
            "plans": [(p.name, is_plan_visible_to(p, STICHTAG, False)) for p in plans],
            "ws": sorted(ws.values()),
            "maria_today": [(ws[s.workstation_id], s.note) for n, s in assigns
                            if n == "maria" and s.weekday == STICHTAG.weekday()],
            "assigned": {(n, ws[s.workstation_id]) for n, s in assigns},
            "quals": quals,
            "entries": db.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID).count(),
        }

    r = _read(app_engine, collect)
    assert r["plans"] == [(seed.SHIFT_PLAN_NAME, True)]
    assert r["ws"] == sorted(name for name, _ in seed.SHIFT_WORKSTATIONS)
    assert ("Anmeldung", "Telefondienst bis 9:00") in r["maria_today"]
    assert r["assigned"] <= r["quals"], "jede Einteilung hat eine Einweisung"
    assert r["entries"] == entries_before


def test_change_requests_have_realistic_timestamps(full_tenant, app_engine, monkeypatch):
    """Tab „Anträge“: Marias offener Antrag ist am Stichtag vor der Aufnahme
    (10:30) gestellt; Thomas' abgelehnter Antrag an einem Werktag nach dem
    Eintrag gestellt und danach bearbeitet – beides vor dem Stichtag."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    seed = _load_seed()
    _run_seed(app_engine, seed, monkeypatch)
    berlin = ZoneInfo("Europe/Berlin")

    def collect(db):
        names = {u.id: u.username for u in db.query(User).filter(User.tenant_id == TENANT_ID)}
        return {names[c.user_id]: (c.original_date, c.created_at, c.reviewed_at)
                for c in db.query(ChangeRequest).filter(ChangeRequest.tenant_id == TENANT_ID)}

    r = _read(app_engine, collect)
    m_date, m_created, m_reviewed = r["maria"]
    assert m_reviewed is None
    assert m_created.astimezone(berlin).date() == STICHTAG
    assert m_created.astimezone(berlin).time() < time(10, 30)
    t_date, t_created, t_reviewed = r["thomas"]
    c, v = t_created.astimezone(berlin), t_reviewed.astimezone(berlin)
    assert t_date < c.date() < v.date() < STICHTAG
    assert c.weekday() < 5 and v.weekday() < 5
    assert c < v < datetime.combine(STICHTAG, time(0), tzinfo=berlin)
