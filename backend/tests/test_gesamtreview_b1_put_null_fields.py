"""Gesamtreview 1.20, Bündel B1 (Punkt 2): ``null`` für ein Pflichtfeld im PUT.

``TimeEntryUpdate`` erlaubt jedes Feld als ``Optional`` — gemeint ist „darf
fehlen", nicht „darf null sein". Die MA-Route übernahm ein mitgeschicktes
``{"date": null}`` per ``setattr`` in die Zeile: für Admins lief danach die
Kappung mit ``None`` als Datum (500), für Mitarbeitende kam der irreführende
403 „Einträge vergangener Tage …" für den heutigen Eintrag. ``start_time`` und
``break_minutes`` endeten ebenso (Vergleich mit ``None`` bzw. NOT-NULL-Spalte).
Jetzt 422 am Schema für beide Routen — ein weggelassenes Feld bleibt
unverändert wie bisher.

Nachzug (Review zu B1): ``end_time`` gehört dazu. Die Spalte ist zwar nullable
(offener Eintrag), ein ``{"end_time": null}`` öffnete über die MA-Route aber
einen geschlossenen Eintrag wieder — §16-Endstempel weg, §3/§4 übersprungen,
beim nächsten Einstempeln schloss ``_close_stale_entry`` ihn um 23:59 (an einem
Tag ohne Blöcke voll angerechnet). Die Admin-Route las dasselbe ``null`` als
„unverändert". Ein offener Eintrag bleibt offen, solange ``end_time`` fehlt.
"""
from datetime import time

import pytest

from app.models import TimeEntry
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON

import app.routers.time_entries as te

ROUTES = ["/api/time-entries", "/api/admin/time-entries"]


def _entry(db, user, d=MON):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=time(8), end_time=time(12), break_minutes=0, note="alt")
    db.add(e)
    db.commit()
    return e


@pytest.mark.parametrize("route", ROUTES, ids=["ma-route", "admin-route"])
@pytest.mark.parametrize("field", ["date", "start_time", "end_time", "break_minutes"])
def test_admin_null_for_a_required_field_is_422(_db_session, employee_user, admin_client,
                                                route, field):
    e = _entry(_db_session, employee_user)
    r = admin_client.put(f"{route}/{e.id}", json={field: None, "note": "neu"})
    assert r.status_code == 422, r.text
    _db_session.expire_all()
    e = _db_session.get(TimeEntry, e.id)
    assert (e.date, e.start_time, e.end_time, e.break_minutes, e.note) == (
        MON, time(8), time(12), 0, "alt")


def test_employee_null_end_does_not_reopen_todays_entry(_db_session, employee_user,
                                                        employee_client, monkeypatch):
    """Nachzug: ein geschlossener heutiger Eintrag bleibt geschlossen — sonst
    entstanden nach erneutem Einstempeln zwei offene Einträge."""
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    e = _entry(_db_session, employee_user)
    r = employee_client.put(f"/api/time-entries/{e.id}", json={"end_time": None})
    assert r.status_code == 422, r.text
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id).end_time == time(12)


def test_open_entry_stays_open_when_end_is_omitted(_db_session, employee_user, employee_client,
                                                   monkeypatch):
    """Kontrolle: so arbeitet die Zeiterfassung — bei einem offenen Eintrag
    fehlt ``end_time`` im PUT, der Eintrag bleibt offen."""
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                  start_time=time(8), end_time=None, break_minutes=0, note="alt")
    _db_session.add(e)
    _db_session.commit()
    r = employee_client.put(f"/api/time-entries/{e.id}", json={"note": "neu"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.end_time, e.note) == (None, "neu")


def test_admin_note_on_open_entry_keeps_it_open(_db_session, employee_user, admin_client):
    """Nachzug: die Admin-Route rechnete §4/§3/48 h/§6 auch ohne Ende (500
    ``'NoneType' object has no attribute 'hour'``). Seit ``{"end_time": null}``
    gesperrt ist, ließ sich eine Notiz an einem laufenden Eintrag sonst nur
    noch zusammen mit einem Ende setzen."""
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                  start_time=time(8), end_time=None, break_minutes=0, note="alt")
    _db_session.add(e)
    _db_session.commit()
    r = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"note": "neu"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.start_time, e.end_time, e.note) == (time(8), None, "neu")


def test_employee_null_date_is_422_not_403(_db_session, employee_user, employee_client,
                                           monkeypatch):
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    e = _entry(_db_session, employee_user)
    r = employee_client.put(f"/api/time-entries/{e.id}", json={"date": None})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("route", ROUTES, ids=["ma-route", "admin-route"])
def test_omitted_fields_stay_unchanged(_db_session, employee_user, admin_client, route):
    """Kontrolle: ein weggelassenes Feld ist weiterhin „unverändert"."""
    e = _entry(_db_session, employee_user)
    r = admin_client.put(f"{route}/{e.id}", json={"note": "neu"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.date, e.start_time, e.end_time, e.note) == (MON, time(8), time(12), "neu")


@pytest.mark.parametrize("route", ROUTES, ids=["ma-route", "admin-route"])
def test_null_note_is_still_allowed(_db_session, employee_user, admin_client, route):
    """Kontrolle: optionale Textfelder dürfen weiter ``null`` sein."""
    e = _entry(_db_session, employee_user)
    r = admin_client.put(f"{route}/{e.id}", json={"note": None,
                                                  "sunday_exception_reason": None})
    assert r.status_code == 200, r.text
