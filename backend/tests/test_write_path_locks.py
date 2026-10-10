"""Spec P5: jeder Schreibpfad für Zeiteinträge nimmt ZUERST die Ankersperre der
Eigentümer-Zeile — vor Puffer, Snapshot-Auflösung, clamp und Zeilensperren."""
import datetime as dt
from datetime import date, time

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

import app.routers.admin_change_requests as acr
import app.routers.admin_time_entries as ate
import app.routers.time_entries as te
from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.routers import admin_helpers
from app.services import work_window_service as wws
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON


@pytest.fixture
def calls(monkeypatch):
    log = []
    real_lock = admin_helpers.lock_user_row

    def spy_lock(db, tenant_id, user_id):
        log.append(("lock", str(user_id)))
        return real_lock(db, tenant_id, user_id)

    for mod in (te, ate, acr, admin_helpers):
        monkeypatch.setattr(mod, "lock_user_row", spy_lock, raising=False)
    for name in ("clamp", "get_grace_minutes", "grace_for_entry", "get_scheduled_blocks"):
        real = getattr(wws, name)

        def make(real, name):
            def spy(*a, **kw):
                log.append((name,))
                return real(*a, **kw)
            return spy

        monkeypatch.setattr(wws, name, make(real, name))
    real_close = te._close_stale_entry

    def spy_close(*a, **kw):
        log.append(("close",))
        return real_close(*a, **kw)

    monkeypatch.setattr(te, "_close_stale_entry", spy_close)

    # Zweite Hälfte von P5 (Spec 7.1: „erst danach werden Eintragszeilen mit
    # ``with_for_update`` geladen"): jede ORM-Abfrage mit FOR UPDATE auf
    # ``time_entries`` landet ebenfalls im Protokoll. Ohne diesen Eintrag
    # bliebe eine Ankersperre HINTER der Zeilensperre unentdeckt — genau die
    # Reihenfolge, die gegen Betriebsferien und Neukappung 40P01 auslöst.
    # SQLite übersetzt FOR UPDATE nicht, das Statement trägt es trotzdem.
    def on_execute(state):
        if (state.is_select
                and getattr(state.statement, "_for_update_arg", None) is not None
                and any(m.class_ is TimeEntry for m in state.all_mappers)):
            log.append(("row_lock",))

    event.listen(Session, "do_orm_execute", on_execute)
    yield log
    event.remove(Session, "do_orm_execute", on_execute)


def assert_row_lock_seen(log):
    """Der Listener auf ``do_orm_execute`` hängt am privaten Attribut
    ``_for_update_arg``. Fiele er nach einem SQLAlchemy-Update stumm aus,
    bestünde jeder Reihenfolge-Test wieder kampflos — deshalb in den Pfaden,
    die eine Eintragszeile sperren, ausdrücklich prüfen, dass er anschlägt."""
    assert ("row_lock",) in log, f"keine Zeilensperre auf time_entries protokolliert: {log}"


def assert_lock_first(log, owner_id):
    locks = [i for i, c in enumerate(log) if c == ("lock", str(owner_id))]
    others = [i for i, c in enumerate(log) if c[0] != "lock"]
    assert locks, f"keine Ankersperre auf {owner_id}: {log}"
    assert not others or locks[0] < others[0], log


def _setup(db, user):
    user.work_blocks = K_BLOCKS
    db.commit()


def _entry(db, user, start, end, d=MON):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=0)
    db.add(e)
    db.commit()
    return e


def _clock(monkeypatch, d, hh):
    monkeypatch.setattr(te, "_today_local", lambda: d)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(d.year, d.month, d.day, hh, 0))


def test_clock_in(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    _clock(monkeypatch, MON, 8)
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    assert_lock_first(calls, employee_user.id)
    assert_row_lock_seen(calls)


def test_clock_out(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    _entry(_db_session, employee_user, time(8), None)
    _clock(monkeypatch, MON, 12)
    assert employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0}).status_code == 200
    assert_lock_first(calls, employee_user.id)
    assert_row_lock_seen(calls)


def test_clock_status_stale_branch(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    _entry(_db_session, employee_user, time(8), None)
    _clock(monkeypatch, date(2026, 6, 2), 8)
    assert employee_client.get("/api/time-entries/clock-status").status_code == 200
    assert ("close",) in calls
    assert_lock_first(calls, employee_user.id)
    assert_row_lock_seen(calls)


def test_create(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    _clock(monkeypatch, MON, 13)
    resp = employee_client.post("/api/time-entries/", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "12:00", "break_minutes": 0})
    assert resp.status_code == 201, resp.text
    assert_lock_first(calls, employee_user.id)


def test_update(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8), time(11))
    _clock(monkeypatch, MON, 13)
    assert employee_client.put(f"/api/time-entries/{e.id}", json={"end_time": "12:00"}).status_code == 200
    assert_lock_first(calls, employee_user.id)
    assert_row_lock_seen(calls)


def test_admin_create(_db_session, employee_user, admin_client, calls):
    _setup(_db_session, employee_user)
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "12:00", "break_minutes": 0})
    assert resp.status_code == 201, resp.text
    assert_lock_first(calls, employee_user.id)


def test_admin_update(_db_session, employee_user, admin_client, calls):
    _setup(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8), time(11))
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "12:00"}).status_code == 200
    assert_lock_first(calls, employee_user.id)
    assert_row_lock_seen(calls)


def test_cr_review(_db_session, employee_user, admin_client, calls):
    _setup(_db_session, employee_user)
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
                       proposed_date=MON, proposed_start_time=time(8), proposed_end_time=time(12),
                       proposed_break_minutes=0, reason="Nachtrag")
    _db_session.add(cr)
    _db_session.commit()
    assert admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"}).status_code == 200
    assert_lock_first(calls, employee_user.id)


def test_clock_status_stale_branch_reads_entry_after_lock(_db_session, employee_user, employee_client, monkeypatch):
    """P5 „danach neu lesen": der Stale-Zweig entscheidet auf dem Stand NACH
    der Ankersperre, nicht auf dem vorher geladenen Objekt der Identity-Map.

    Ein paralleler Schreiber hat den offenen Eintrag während der Wartezeit
    auf heute verlegt (Core-UPDATE an der Identity-Map vorbei, wie eine fremde,
    inzwischen committete Transaktion). Ohne frisches Lesen schlösse der Zweig
    den heute laufenden Eintrag auf 23:59."""
    _setup(_db_session, employee_user)
    entry_id = _entry(_db_session, employee_user, time(8), None).id
    tuesday = date(2026, 6, 2)
    _clock(monkeypatch, tuesday, 9)
    # Der Zweig „eingestempelt" rechnet mit zeitzonenbehafteter Uhrzeit.
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 2, 9, 0, tzinfo=te.LOCAL_TZ))
    real_lock = admin_helpers.lock_user_row

    def lock_then_parallel_move(db, tenant_id, user_id):
        row = real_lock(db, tenant_id, user_id)
        tbl = TimeEntry.__table__
        db.execute(tbl.update().where(tbl.c.id == entry_id).values(date=tuesday))
        return row

    monkeypatch.setattr(te, "lock_user_row", lock_then_parallel_move)
    resp = employee_client.get("/api/time-entries/clock-status")
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_clocked_in"] is True
    _db_session.expire_all()
    stored = _db_session.get(TimeEntry, entry_id)
    assert (stored.date, stored.end_time) == (tuesday, None)


def test_xls_import(_db_session, employee_user, admin_user, calls):
    """P5: ``_execute_import_inner`` sperrt die Zielperson EINMAL am Anfang —
    vor Puffer, Snapshot und clamp (lokaler Import → Spy über admin_helpers)."""
    from app.services.xls_import_service import ImportedEntry, execute_import

    _setup(_db_session, employee_user)
    row = ImportedEntry(date=MON, start_time=time(8), end_time=time(12), break_minutes=0,
                        note=None, has_conflict=False, arbzg_warnings=[])
    result = execute_import(employee_user.id, [row], overwrite=False, db=_db_session,
                            changed_by_id=admin_user.id, filename="t.xls", tenant_id=DEFAULT_TENANT_ID)
    assert result.imported == 1
    assert_lock_first(calls, employee_user.id)


def _other_employee(db):
    from app.models import User
    from app.models.user import UserRole
    from app.services import auth_service

    other = User(username="kollegin", email="kollegin@test.de",
                 password_hash=auth_service.hash_password("Kollegin2025!"),
                 first_name="Erika", last_name="Musterfrau", role=UserRole.EMPLOYEE,
                 weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
                 is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(other)
    db.commit()
    db.refresh(other)
    return other


def test_update_foreign_entry_takes_no_lock(_db_session, employee_user, employee_client, calls, monkeypatch):
    """Härtung nach P5: der Eigentümer wird ungesperrt gelesen, damit die
    Ankersperre VOR jeder Zeilensperre liegt. Ein Mitarbeiter, der die ID eines
    FREMDEN Eintrags schickt, darf dabei weder die Benutzerzeile der Kollegin
    noch deren Eintragszeile sperren — sonst könnte er fremde Schreibpfade
    blockieren und an der Wartezeit ablesen, dass die ID existiert
    (Timing-Orakel neben dem #120-404)."""
    other = _other_employee(_db_session)
    e = _entry(_db_session, other, time(8), time(11))
    _clock(monkeypatch, MON, 13)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"end_time": "12:00"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Zeiteintrag nicht gefunden"
    assert not [c for c in calls if c[0] == "lock"], calls
    assert ("row_lock",) not in calls, calls
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id).end_time == time(11)


def test_delete_foreign_entry_takes_no_lock(_db_session, employee_user, employee_client, calls, monkeypatch):
    """Gegenstück zum Bearbeiten: auch der Löschpfad sperrt für einen fremden
    Eintrag nichts, bevor die Eigentümerprüfung mit 404 abbricht."""
    other = _other_employee(_db_session)
    e = _entry(_db_session, other, time(8), time(11))
    _clock(monkeypatch, MON, 13)
    resp = employee_client.delete(f"/api/time-entries/{e.id}")
    assert resp.status_code == 404, resp.text
    assert not [c for c in calls if c[0] == "lock"], calls
    assert ("row_lock",) not in calls, calls
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is not None
