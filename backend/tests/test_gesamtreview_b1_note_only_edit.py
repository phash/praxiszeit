"""Gesamtreview 1.20, Bündel B1 (Punkt 4): Bearbeiten ohne Zeitänderung.

Ein anerkannter Eintrag (13.3, P4) darf §3/§4 überschreiten — beim Anerkennen
kommen sie nur als weiche Warnung. Danach scheiterte aber jede Admin-
Bearbeitung an den HARTEN Prüfungen, auch eine reine Notiz oder das
unveränderte Formular (AdminDashboard und Monatsjournal schicken Beginn, Ende
und Pause immer mit): §4 → 400, §3 → 422. Eine Bearbeitung, die Datum,
angerechneten Beginn/Ende, Pause und nicht angerechnete Minuten nicht ändert,
ändert auch nichts an §3/§4 — sie wird dort nicht mehr abgelehnt. Wer die
Zeiten ändert, wird weiter hart geprüft.
"""
from datetime import time

import pytest

from app.models import TimeEntry
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON

ROUTES = ["/api/admin/time-entries", "/api/time-entries"]
IDS = ["admin-route", "ma-route"]


def _recognized(db, user, start=time(7), end=time(19), **kw):
    """Anerkannt 07:00–19:00 ohne Pause: 12 h (§3) und keine §4-Pause."""
    user.work_blocks = K_BLOCKS
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON, start_time=start,
                  end_time=end, break_minutes=0, uncredited_minutes=0, credit_override=True,
                  clamp_grace_minutes=15, note="alt", **kw)
    db.add(e)
    db.commit()
    return e


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_note_only_edit_of_a_recognized_long_entry(_db_session, employee_user, admin_client, route):
    e = _recognized(_db_session, employee_user)
    r = admin_client.put(f"{route}/{e.id}", json={"note": "geprüft"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.start_time, e.end_time, e.break_minutes, e.note, e.credit_override) == (
        time(7), time(19), 0, "geprüft", True)


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_unchanged_form_resave_of_a_recognized_entry(_db_session, employee_user, admin_client,
                                                     route):
    """Das Formular schickt alle Felder unverändert mit."""
    e = _recognized(_db_session, employee_user)
    r = admin_client.put(f"{route}/{e.id}", json={
        "date": MON.isoformat(), "start_time": "07:00", "end_time": "19:00",
        "break_minutes": 0, "note": "geprüft"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.note, e.credit_override) == ("geprüft", True)


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_recognized_entry_without_break_note_only(_db_session, employee_user, admin_client, route):
    """Nur §4: 07:00–16:30 = 9,5 h ohne Pause (≤ 10 h)."""
    e = _recognized(_db_session, employee_user, end=time(16, 30))
    r = admin_client.put(f"{route}/{e.id}", json={"note": "geprüft"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_changed_times_are_still_checked_hard(_db_session, employee_user, admin_client, route):
    """Kontrolle: wer die Zeiten ändert, wird weiter hart geprüft — §4 (ohne
    Begründung) bzw. §3."""
    e = _recognized(_db_session, employee_user)
    r = admin_client.put(f"{route}/{e.id}", json={"end_time": "19:30", "break_minutes": 0})
    assert r.status_code in (400, 422), r.text
    _db_session.rollback()
    _db_session.refresh(e)
    assert (e.end_time, e.note) == (time(19), "alt")


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_changed_break_is_still_checked_hard(_db_session, employee_user, admin_client, route):
    """Kontrolle: eine Pausenänderung ist eine Zeitänderung (§3 bleibt > 10 h)."""
    e = _recognized(_db_session, employee_user)
    r = admin_client.put(f"{route}/{e.id}", json={"break_minutes": 45})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_unchanged_edit_with_a_reason_still_documents_the_exception(
        _db_session, employee_user, admin_client, route):
    """Kontrolle: kommt eine Begründung mit, bleibt §4 eine Prüfung — die
    Ausnahme wird wie bisher dokumentiert (Warnung ``BREAK_WAIVER``, Protokoll)."""
    e = _recognized(_db_session, employee_user, end=time(16, 30))
    r = admin_client.put(f"{route}/{e.id}", json={"note": "geprüft",
                                                  "break_waiver_reason": "Notfall"})
    assert r.status_code == 200, r.text
    assert any(w.startswith("BREAK_WAIVER") for w in r.json()["warnings"]), r.json()["warnings"]
    _db_session.refresh(e)
    assert e.break_waiver_reason == "Notfall"
