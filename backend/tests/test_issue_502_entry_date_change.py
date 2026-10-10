"""#502: Mitarbeitende verschieben einen Zeiteintrag nicht per ``PUT`` auf einen
anderen Tag.

``update_time_entry`` prüfte für Nicht-Admins nur das GESPEICHERTE Datum.
``{"date": "<vergangener Sonntag>"}`` auf den heutigen, noch offenen Eintrag
lief ohne Ende an §3/§4 und am End>Start-Check vorbei, und der Auto-Close aus
``GET /clock-status`` schloss ihn danach um 23:59 — bis zu rund 16 h an einem
vergangenen Tag, ohne Änderungsantrag. Einträge vergangener Tage ändern
Mitarbeitende nur per Antrag; Anlegen und Löschen setzten das bereits durch.

Zusätzlich: ein Datumswechsel prüft das Beschäftigungsfenster der Person des
Eintrags (wie ``create_time_entry``) — auf beiden Bearbeiten-Routen, und das
Admin-Anlegen (``admin_create_time_entry``) ebenso —, und
``TimeEntryUpdate.date`` lehnt ein Datum in der Zukunft ab (wie
``TimeEntryBase``)."""
import datetime as dt
from datetime import date, time, timedelta

import pytest

from app.models import TimeEntry
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON

import app.routers.time_entries as te

FRI_BEFORE = date(2026, 5, 29)
PAST_SUNDAY = date(2026, 5, 31)
LOCK_TEXT = "Einträge vergangener Tage können nur per Änderungsantrag geändert werden"


def _entry(db, user, d, start=time(8, 0), end=time(16, 0), brk=30, note=None):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=brk if end else 0,
                  note=note)
    db.add(e)
    db.commit()
    return e


@pytest.fixture
def today_is_monday(monkeypatch):
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 12, 0))


# ── (a) Mitarbeitende: kein Datumswechsel weg von heute ──────────────────────

def test_employee_cannot_move_open_entry_to_past_sunday(_db_session, employee_user, employee_client, today_is_monday):
    """Die Angriffskette aus dem Ticket: heute eingestempelt, Datum auf den
    vergangenen Sonntag gesetzt — ohne Ende liefen §3/§4 gar nicht."""
    e = _entry(_db_session, employee_user, MON, end=None)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"date": PAST_SUNDAY.isoformat()})
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == LOCK_TEXT
    _db_session.refresh(e)
    assert (e.date, e.end_time) == (MON, None)


def test_employee_cannot_move_closed_entry_to_past_day(_db_session, employee_user, employee_client, today_is_monday):
    """Auch mit Ende und weiteren Feldern im selben PUT: abgelehnt, bevor
    irgendein Feld übernommen wird."""
    e = _entry(_db_session, employee_user, MON, note="alt")
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={
        "date": FRI_BEFORE.isoformat(), "note": "neu", "start_time": "07:00"})
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == LOCK_TEXT
    _db_session.refresh(e)
    assert (e.date, e.start_time, e.note) == (MON, time(8, 0), "alt")


def test_employee_may_resubmit_todays_date(_db_session, employee_user, employee_client, today_is_monday):
    """Kontrolltest: das Bearbeiten-Formular schickt das (heutige) Datum immer
    mit — das bleibt erlaubt."""
    e = _entry(_db_session, employee_user, MON)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={
        "date": MON.isoformat(), "note": "Nachtrag"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.date, e.note) == (MON, "Nachtrag")


# ── (c) Schema: kein Datum in der Zukunft ────────────────────────────────────

def test_employee_future_date_rejected_by_schema(_db_session, employee_user, employee_client):
    e = _entry(_db_session, employee_user, today_local())
    tomorrow = today_local() + timedelta(days=1)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"date": tomorrow.isoformat()})
    assert resp.status_code == 422, resp.text
    assert "Zukunft" in resp.text
    _db_session.refresh(e)
    assert e.date == today_local()


@pytest.mark.parametrize("route", ["/api/time-entries/{id}", "/api/admin/time-entries/{id}"])
def test_admin_future_date_rejected_by_schema(_db_session, employee_user, admin_client, route):
    """``TimeEntryUpdate`` trägt auch die Admin-Route — Anlegen in der Zukunft
    lehnt ``TimeEntryCreate`` dort bereits ab, Verschieben jetzt ebenso."""
    e = _entry(_db_session, employee_user, FRI_BEFORE)
    tomorrow = today_local() + timedelta(days=1)
    resp = admin_client.put(route.format(id=e.id), json={"date": tomorrow.isoformat()})
    assert resp.status_code == 422, resp.text
    assert "Zukunft" in resp.text
    _db_session.refresh(e)
    assert e.date == FRI_BEFORE


# ── (b) Beschäftigungsfenster der Person des Eintrags ────────────────────────
# Beide Routen, die ein Datum verschieben: die MA-Route (Admins bearbeiten dort
# auch fremde Einträge) UND ``admin_update_time_entry`` — die Fläche, über die
# AdminDashboard und Monatsjournal fremde Einträge tatsächlich bearbeiten.
# Ohne die Prüfung dort landete ein Eintrag vor dem ersten Arbeitstag, und die
# Ist-Rechnung (Fenster, #195) liess seine Stunden still aus dem Saldo fallen.

UPDATE_ROUTES = ["/api/time-entries/{id}", "/api/admin/time-entries/{id}"]


@pytest.mark.parametrize("route", UPDATE_ROUTES)
def test_date_change_before_first_work_day_rejected(_db_session, employee_user, admin_user, admin_client, route):
    employee_user.first_work_day = MON
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON)
    resp = admin_client.put(route.format(id=e.id), json={"date": FRI_BEFORE.isoformat()})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "Datum liegt vor dem ersten Arbeitstag"
    _db_session.refresh(e)
    assert e.date == MON


@pytest.mark.parametrize("route", UPDATE_ROUTES)
def test_date_change_after_last_work_day_rejected(_db_session, employee_user, admin_user, admin_client, route):
    employee_user.last_work_day = date(2026, 5, 27)
    _db_session.commit()
    e = _entry(_db_session, employee_user, date(2026, 5, 25))
    resp = admin_client.put(route.format(id=e.id), json={"date": FRI_BEFORE.isoformat()})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "Datum liegt nach dem letzten Arbeitstag"
    _db_session.refresh(e)
    assert e.date == date(2026, 5, 25)


@pytest.mark.parametrize("route", UPDATE_ROUTES)
def test_window_check_uses_entry_owner_not_admin(_db_session, employee_user, admin_user, admin_client, route):
    """Admins bearbeiten fremde Einträge — maßgeblich ist das Fenster der
    Person des Eintrags, nicht das der bearbeitenden Admin."""
    admin_user.first_work_day = MON
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON)
    resp = admin_client.put(route.format(id=e.id), json={"date": FRI_BEFORE.isoformat()})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.date == FRI_BEFORE


@pytest.mark.parametrize("route", UPDATE_ROUTES)
def test_unchanged_date_outside_window_does_not_block_edit(_db_session, employee_user, admin_user, admin_client, route):
    """Nur ein WECHSEL des Datums wird geprüft: das Formular schickt das
    gespeicherte Datum immer mit. Ein Alteintrag außerhalb eines später
    gesetzten Fensters bleibt per Notiz-/Zeitkorrektur reparierbar."""
    employee_user.first_work_day = MON
    _db_session.commit()
    e = _entry(_db_session, employee_user, FRI_BEFORE)
    resp = admin_client.put(route.format(id=e.id), json={
        "date": FRI_BEFORE.isoformat(), "note": "korrigiert"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.date, e.note) == (FRI_BEFORE, "korrigiert")


# ── (d) Admin-Anlegen: dasselbe Fenster wie beim MA-Anlegen ──────────────────
# Parallelpfad zu ``create_time_entry``: das Monatsjournal und das
# AdminDashboard legen fremde Einträge über ``admin_create_time_entry`` an.

def _admin_create(admin_client, user, d):
    return admin_client.post(f"/api/admin/users/{user.id}/time-entries", json={
        "date": d.isoformat(), "start_time": "08:00", "end_time": "12:00", "break_minutes": 0})


def _entries_on(db, user, d):
    return db.query(TimeEntry).filter(TimeEntry.user_id == user.id, TimeEntry.date == d).count()


def test_admin_create_before_first_work_day_rejected(_db_session, employee_user, admin_user, admin_client):
    employee_user.first_work_day = MON
    _db_session.commit()
    resp = _admin_create(admin_client, employee_user, FRI_BEFORE)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "Datum liegt vor dem ersten Arbeitstag"
    assert _entries_on(_db_session, employee_user, FRI_BEFORE) == 0


def test_admin_create_after_last_work_day_rejected(_db_session, employee_user, admin_user, admin_client):
    employee_user.last_work_day = date(2026, 5, 27)
    _db_session.commit()
    resp = _admin_create(admin_client, employee_user, FRI_BEFORE)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "Datum liegt nach dem letzten Arbeitstag"
    assert _entries_on(_db_session, employee_user, FRI_BEFORE) == 0


def test_admin_create_uses_target_window_not_admin(_db_session, employee_user, admin_user, admin_client):
    """Kontrolltest: das Fenster der ADMIN spielt beim Anlegen für eine andere
    Person keine Rolle."""
    admin_user.first_work_day = MON
    _db_session.commit()
    resp = _admin_create(admin_client, employee_user, FRI_BEFORE)
    assert resp.status_code == 201, resp.text
    assert _entries_on(_db_session, employee_user, FRI_BEFORE) == 1
