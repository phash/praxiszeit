"""Teil A, Task 9: „Stundenzählung" (``track_hours``) in Dashboard, Berichten,
Betriebsferien, Teamübersicht und Benutzerübersicht aus dem Vertrags-Snapshot
zum jeweiligen Datum — nie aus der Live-Spalte der User-Zeile.

Review Focus 2: eine zukunftsdatierte Zeile, die die Stundenzählung abschaltet,
wird ohne jedes Schreiben gültig (kein Scheduler spiegelt sie in ``users``).
„Heute"-Fragen lesen deshalb den Snapshot von heute."""
import datetime as dt
import uuid
from datetime import date

from fastapi.testclient import TestClient

import app.routers.auth as auth_router
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, WorkingHoursChange
from app.models.system_setting import SystemSetting
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_user, employee_user, endpoints_app, tenant,
)
from tests.wh_change_helpers import add_row, entry, freeze, t

DEC_MON, DEC_THU = date(2026, 12, 7), date(2026, 12, 10)
MAR_MON, MAR_TUE, MAR_WED, MAR_THU = (date(2026, 3, 9), date(2026, 3, 10),
                                      date(2026, 3, 11), date(2026, 3, 12))


def _client(db, user, *, admin=False) -> TestClient:
    def _override_db():
        yield db
    endpoints_app.dependency_overrides.clear()
    endpoints_app.dependency_overrides[get_db] = _override_db
    endpoints_app.dependency_overrides[get_current_user] = lambda: user
    if admin:
        endpoints_app.dependency_overrides[require_admin] = lambda: user
    return TestClient(endpoints_app)


def _off_from_december(db, user):
    """Stundenzählung bis November, ab 01.12.2026 aus — die User-Zeile bleibt
    auf True (zukunftsdatierte Zeile, noch nicht gespiegelt)."""
    add_row(db, user, date(2026, 1, 1), weekly_hours=40, track_hours=True)
    add_row(db, user, date(2026, 12, 1), weekly_hours=40, track_hours=False)
    db.refresh(user)
    assert user.track_hours is True


def test_tracks_hours_in_range(_db_session, employee_user):
    db, u = _db_session, employee_user
    _off_from_december(db, u)
    assert cs.tracks_hours_in_range(db, u, date(2026, 12, 1), date(2026, 12, 31)) is False
    assert cs.tracks_hours_in_range(db, u, date(2026, 11, 1), date(2026, 11, 30)) is True
    assert cs.tracks_hours_in_range(db, u, date(2026, 11, 30), date(2026, 12, 6)) is True
    rows = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == u.id).all()
    assert cs.tracks_hours_in_range(db, u, date(2026, 12, 1), date(2026, 12, 31), rows) is False
    # Wieder eingeschaltet mitten im Zeitraum → irgendein Tag zählt.
    add_row(db, u, date(2027, 1, 15), weekly_hours=40, track_hours=True)
    assert cs.tracks_hours_in_range(db, u, date(2027, 1, 1), date(2027, 1, 31)) is True
    assert cs.tracks_hours_in_range(db, u, date(2027, 1, 1), date(2027, 1, 14)) is False


def test_future_row_switching_track_hours_off_applies_without_mirror(
        _db_session, employee_user, admin_user, monkeypatch):   # Review Focus 2
    db, u = _db_session, employee_user
    _off_from_december(db, u)
    entry(db, u, date(2026, 12, 1), t(8), None)       # offener Eintrag → wäre „Buchung fehlt"
    freeze(monkeypatch, date(2026, 12, 2))
    try:
        emp = _client(db, u)
        assert emp.get("/api/dashboard/missing-bookings").json()["entries"] == []
        # F025: die Woche 30.11.–06.12. hat mit dem 30.11. einen gezählten Tag →
        # sie erscheint (wie in den Admin-Berichten, tracks_hours_in_range).
        assert [w["week_start"] for w in emp.get("/api/dashboard/weekly-overview").json()] == [
            "2026-11-30"]
        adm = _client(db, admin_user, admin=True)
        team = adm.get("/api/dashboard/missing-bookings/team")
        assert team.status_code == 200, team.text
        ids = [x["user_id"] for x in team.json()]
        assert str(u.id) not in ids
        assert str(admin_user.id) in ids          # ohne Verlauf: User-Zeile (True), Dez. ohne Buchung
        overview = {r["user_id"]: r for r in adm.get("/api/admin/users-overview").json()}
        assert overview[str(u.id)]["track_hours"] is False
        assert overview[str(admin_user.id)]["track_hours"] is True
    finally:
        endpoints_app.dependency_overrides.clear()


def test_missing_bookings_still_reported_before_the_switch(_db_session, employee_user, monkeypatch):
    db, u = _db_session, employee_user
    _off_from_december(db, u)
    entry(db, u, date(2026, 11, 2), t(8), None)
    freeze(monkeypatch, date(2026, 11, 4))
    try:
        body = _client(db, u).get("/api/dashboard/missing-bookings").json()
        assert [e["type"] for e in body["entries"]][:1] == ["open"]
    finally:
        endpoints_app.dependency_overrides.clear()


def test_open_entry_of_tracked_day_reported_after_switch_off(_db_session, employee_user, monkeypatch):
    """F025: heute ohne Stundenzählung — der offene Eintrag eines früheren Tages
    MIT Stundenzählung bleibt als „offen" sichtbar (er muss noch beendet werden)."""
    db, u = _db_session, employee_user
    _off_from_december(db, u)
    entry(db, u, date(2026, 11, 30), t(8), None)
    freeze(monkeypatch, date(2026, 12, 2))
    try:
        body = _client(db, u).get("/api/dashboard/missing-bookings").json()
        assert [(e["date"], e["type"]) for e in body["entries"]] == [("2026-11-30", "open")]
    finally:
        endpoints_app.dependency_overrides.clear()


def test_my_work_schedule_track_hours_from_todays_snapshot(_db_session, employee_user, monkeypatch):
    db, u = _db_session, employee_user
    _off_from_december(db, u)
    monkeypatch.setattr(auth_router, "now_local", lambda: dt.datetime(2026, 12, 2, 10, 0))
    try:
        assert _client(db, u).get("/api/auth/me/work-schedule").json()["track_hours"] is False
        monkeypatch.setattr(auth_router, "now_local", lambda: dt.datetime(2026, 11, 2, 10, 0))
        assert _client(db, u).get("/api/auth/me/work-schedule").json()["track_hours"] is True
    finally:
        endpoints_app.dependency_overrides.clear()


def _closure(client, start, end):
    r = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": start.isoformat(), "end_date": end.isoformat(),
        "counts_as_vacation": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _closure_rows(db, user, closure_id):
    return db.query(Absence).filter(
        Absence.user_id == user.id, Absence.closure_id == uuid.UUID(closure_id),
    ).order_by(Absence.date).all()


def test_closure_on_untracked_day_books_vacation_day_without_hours(_db_session, employee_user, admin_user):
    db, u = _db_session, employee_user
    _off_from_december(db, u)
    try:
        c = _closure(_client(db, admin_user, admin=True), DEC_MON, DEC_THU)
    finally:
        endpoints_app.dependency_overrides.clear()
    rows = _closure_rows(db, u, c["id"])
    assert [a.date for a in rows] == [DEC_MON, date(2026, 12, 8), date(2026, 12, 9), DEC_THU]
    assert all(a.type == AbsenceType.VACATION for a in rows)
    assert all(float(a.hours) == 0 and a.half_day is False for a in rows)
    assert cs.get_vacation_account(db, u, 2026)["used_days"] == 4.0


def _toggle_split(db):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID, value="true"))
    db.commit()


def test_closure_split_mixed_year(_db_session, employee_user, admin_user):
    """Ohne Stundenzählung bis Di., ab Mi. mit; 2 Tage Urlaub. Die beiden
    ungezählten Tage sind Urlaub (tagebasiert, verbrauchen das Budget), die
    gezählten Tage danach nehmen am Split teil → Überstundenausgleich."""
    db, u = _db_session, employee_user
    add_row(db, u, date(2026, 1, 1), weekly_hours=40, track_hours=False, vacation_days=2)
    add_row(db, u, MAR_WED, weekly_hours=40, track_hours=True, vacation_days=2)
    _toggle_split(db)
    try:
        c = _closure(_client(db, admin_user, admin=True), MAR_MON, MAR_THU)
    finally:
        endpoints_app.dependency_overrides.clear()
    rows = _closure_rows(db, u, c["id"])
    assert [(a.date, a.type) for a in rows] == [
        (MAR_MON, AbsenceType.VACATION), (MAR_TUE, AbsenceType.VACATION),
        (MAR_WED, AbsenceType.OVERTIME), (MAR_THU, AbsenceType.OVERTIME),
    ]
    assert [float(a.hours) for a in rows] == [0, 0, 8, 8]


def test_closure_split_untracked_days_after_tracked_stay_vacation(_db_session, employee_user, admin_user):
    """Mit Stundenzählung bis Di., ab Mi. ohne; 2 Tage Urlaub. Mo./Di. verbrauchen
    das Budget, Mi./Do. bleiben Urlaub (kein Überstundenkonto an ungezählten Tagen)."""
    db, u = _db_session, employee_user
    add_row(db, u, date(2026, 1, 1), weekly_hours=40, track_hours=True, vacation_days=2)
    add_row(db, u, MAR_WED, weekly_hours=40, track_hours=False, vacation_days=2)
    _toggle_split(db)
    try:
        c = _closure(_client(db, admin_user, admin=True), MAR_MON, MAR_THU)
    finally:
        endpoints_app.dependency_overrides.clear()
    rows = _closure_rows(db, u, c["id"])
    assert [a.type for a in rows] == [AbsenceType.VACATION] * 4
    assert [float(a.hours) for a in rows] == [8, 8, 0, 0]


def test_reports_monthly_track_hours_flag_per_period(_db_session, employee_user, admin_user):
    db, u = _db_session, employee_user
    _off_from_december(db, u)
    try:
        adm = _client(db, admin_user, admin=True)

        def flag(path):
            r = adm.get(path)
            assert r.status_code == 200, r.text
            return {x["user_id"]: x["track_hours"] for x in r.json()}[str(u.id)]

        assert flag("/api/admin/reports/monthly?month=2026-11") is True
        assert flag("/api/admin/reports/monthly?month=2026-12") is False
        assert flag("/api/admin/reports/weekly?week_start=2026-11-30") is True   # Mo 30.11. zählt
        assert flag("/api/admin/reports/weekly?week_start=2026-12-07") is False
    finally:
        endpoints_app.dependency_overrides.clear()


def test_team_schedule_uses_snapshot_at_date(_db_session, employee_user, admin_user):
    db, u = _db_session, employee_user
    _off_from_december(db, u)
    try:
        adm = _client(db, admin_user, admin=True)

        def flag(d):
            r = adm.get(f"/api/admin/team-schedule?date={d.isoformat()}")
            assert r.status_code == 200, r.text
            return {x["user_id"]: x["track_hours"] for x in r.json()}[str(u.id)]

        assert flag(date(2026, 11, 5)) is True
        assert flag(date(2026, 12, 5)) is False
    finally:
        endpoints_app.dependency_overrides.clear()


def test_me_contract_fields_from_todays_snapshot(_db_session, employee_user, monkeypatch):
    """F006: /auth/me liefert Stundenzählung, Anspruch und Minijob-Felder aus dem
    HEUTE gültigen Snapshot, nicht aus der (noch nicht gespiegelten) User-Zeile."""
    db, u = _db_session, employee_user
    _off_from_december(db, u)              # User-Zeile bleibt track_hours=True
    freeze(monkeypatch, date(2026, 12, 2))
    try:
        me = _client(db, u).get("/api/auth/me").json()
        assert me["track_hours"] is False
        assert me["schedule_today"]["track_hours"] is False
    finally:
        endpoints_app.dependency_overrides.clear()


def test_day_blocks_and_clock_status_on_untracked_snapshot_day(_db_session, employee_user, monkeypatch):
    """F135 (5): ein Tag OHNE Stundenzählung laut Snapshot liefert keine Blöcke und
    kein „Werktag ohne Blöcke" (nichts wird gekappt, kein Soll); der Tag davor
    (mit Stundenzählung, gleiche Blöcke) liefert sie."""
    from tests.work_blocks_fixtures import block_week
    import app.routers.time_entries as te
    db, u = _db_session, employee_user
    week = block_week(mon=[("08:00", "12:00")], tue=[("08:00", "12:00")], wed=[("08:00", "12:00")],
                      thu=[("08:00", "12:00")], fri=[("08:00", "12:00")])
    add_row(db, u, date(2026, 1, 1), week=week, track_hours=True)
    add_row(db, u, date(2026, 12, 1), week=week, track_hours=False)
    freeze(monkeypatch, date(2026, 12, 8))
    monkeypatch.setattr(te, "_today_local", lambda: date(2026, 12, 8))
    try:
        c = _client(db, u)
        tracked = c.get("/api/time-entries/day-blocks", params={"date": "2026-11-24"}).json()
        assert tracked["blocks"] and tracked["blockless_workday"] is False
        untracked = c.get("/api/time-entries/day-blocks", params={"date": "2026-12-08"}).json()
        assert untracked["blocks"] == [] and untracked["blockless_workday"] is False
        status = c.get("/api/time-entries/clock-status").json()
        assert status["today_target_hours"] == 0.0
        assert status["blockless_workday"] is False
    finally:
        endpoints_app.dependency_overrides.clear()


def _fixed_from_july(db, u):
    """Fester Monats-Soll (Minijob, 43,3 h) erst ab 01.07.2026; User-Zeile = Spiegel von heute."""
    from decimal import Decimal
    off = dict(milog_working_time_account=False, agreed_monthly_hours=None, use_fixed_monthly_target=False)
    on = dict(milog_working_time_account=True, agreed_monthly_hours=Decimal("43.3"), use_fixed_monthly_target=True)
    add_row(db, u, date(2026, 1, 1), weekly_hours=10, vacation_days=Decimal("30"), track_hours=True, **off)
    add_row(db, u, date(2026, 7, 1), weekly_hours=10, vacation_days=Decimal("30"), track_hours=True, **on)


def test_mid_year_fixed_mode_switch_in_journal_work_schedule_and_team(_db_session, employee_user,
                                                                      admin_user, monkeypatch):
    """F135 (6): Journal-Zusammenfassung, ``/me/work-schedule`` und Teamübersicht
    lesen den Monatsvertrag des Monats/Datums — Juni Tagesrechnung, Juli fest."""
    from app.services import journal_service
    db, u = _db_session, employee_user
    _fixed_from_july(db, u)
    try:
        assert journal_service.get_journal(db, u, 2026, 6)["use_fixed_monthly_target"] is False
        july = journal_service.get_journal(db, u, 2026, 7)
        assert july["use_fixed_monthly_target"] is True
        assert july["monthly_summary"]["target_hours"] == 43.3

        monkeypatch.setattr(auth_router, "now_local", lambda: dt.datetime(2026, 6, 15, 10, 0))
        assert _client(db, u).get("/api/auth/me/work-schedule").json()["fixed_monthly_hours"] is None
        monkeypatch.setattr(auth_router, "now_local", lambda: dt.datetime(2026, 7, 15, 10, 0))
        assert _client(db, u).get("/api/auth/me/work-schedule").json()["fixed_monthly_hours"] == 43.3

        adm = _client(db, admin_user, admin=True)

        def fixed(d):
            r = adm.get(f"/api/admin/team-schedule?date={d}")
            assert r.status_code == 200, r.text
            return {x["user_id"]: x["use_fixed_monthly_target"] for x in r.json()}[str(u.id)]

        assert fixed("2026-06-30") is False
        assert fixed("2026-07-01") is True
    finally:
        endpoints_app.dependency_overrides.clear()
