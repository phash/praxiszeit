"""Gesamtreview 1.20, Bündel B1 (Nachzug zu Punkt 4): eine schon dokumentierte
§4-Ausnahme ist beim Bearbeiten ohne Zeitänderung keine NEUE Ausnahme.

Das Bearbeiten-Formular der Zeiterfassung belegt Haken und Begründung mit dem
gespeicherten ``break_waiver_reason`` vor und schickt beides beim Speichern
mit. ``update_time_entry`` wertete die unverändert zurückgeschickte Begründung
als neue Ausnahme: Mit ``break_exception_requires_approval`` wurde eine reine
Notizkorrektur an einem Eintrag, den das Ausstempeln mit Begründung sofort
geschlossen hatte (Entscheidung 2026-10-12), zum Genehmigungsantrag (202),
die Notiz blieb stehen. Bei abgeschalteter Ausnahme (#499) kam 400.

Jetzt löst nur eine GEÄNDERTE Begründung (oder eine Zeitänderung) §4 aus.
Ohne Zeitänderung bleibt die dokumentierte Ausnahme außerdem stehen, solange
der §4-Befund unverändert besteht — auch wenn die Begründung leer oder
``null`` mitkommt (sonst verschwand die Dokumentation still).
"""
from datetime import time

import pytest

import app.routers.time_entries as te
from app.models import ChangeRequest, TimeEntry
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON

FORM = {"date": MON.isoformat(), "start_time": "07:00", "end_time": "16:30",
        "break_minutes": 0}


def _setting(db, key, value):
    db.add(SystemSetting(key=key, tenant_id=DEFAULT_TENANT_ID, value=value, description=key))
    db.commit()


def _waived(db, user):
    """07:00–16:30 ohne Pause (9,5 h, §4 verlangt 45 Min.), Ausnahme „Notfall"
    dokumentiert — so speichert das Ausstempeln mit Begründung."""
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON, start_time=time(7),
                  end_time=time(16, 30), break_minutes=0, uncredited_minutes=0, note="alt",
                  break_waiver_reason="Notfall")
    db.add(e)
    db.commit()
    return e


def _crs(db, user):
    return db.query(ChangeRequest).filter(ChangeRequest.user_id == user.id).count()


@pytest.fixture
def today_is_mon(monkeypatch):
    monkeypatch.setattr(te, "_today_local", lambda: MON)


def test_note_with_prefilled_reason_and_approval_is_saved_directly(
        _db_session, employee_user, employee_client, today_is_mon):
    _setting(_db_session, "break_exception_requires_approval", "true")
    e = _waived(_db_session, employee_user)
    r = employee_client.put(f"/api/time-entries/{e.id}",
                            json={**FORM, "note": "neu", "break_waiver_reason": "Notfall"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.note, e.break_waiver_reason) == ("neu", "Notfall")
    assert _crs(_db_session, employee_user) == 0
    # Keine erneute Dokumentation derselben Ausnahme.
    assert not any(w.startswith("BREAK_WAIVER") for w in r.json()["warnings"])


def test_note_with_prefilled_reason_when_exception_is_switched_off(
        _db_session, employee_user, employee_client, today_is_mon):
    """#499: der Schalter sperrt NEUE Ausnahmen; die bestehende Dokumentation
    blockiert die Notizkorrektur nicht."""
    _setting(_db_session, "break_exception_allowed", "false")
    e = _waived(_db_session, employee_user)
    r = employee_client.put(f"/api/time-entries/{e.id}",
                            json={**FORM, "note": "neu", "break_waiver_reason": "Notfall"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.note, e.break_waiver_reason) == ("neu", "Notfall")


@pytest.mark.parametrize("reason", ["", None], ids=["leer", "null"])
def test_unchanged_times_keep_the_documented_exception(
        _db_session, employee_user, employee_client, today_is_mon, reason):
    """Der §4-Befund besteht unverändert — die Dokumentation dazu bleibt."""
    e = _waived(_db_session, employee_user)
    r = employee_client.put(f"/api/time-entries/{e.id}",
                            json={**FORM, "note": "neu", "break_waiver_reason": reason})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.note, e.break_waiver_reason) == ("neu", "Notfall")


def test_changed_reason_still_goes_through_approval(
        _db_session, employee_user, employee_client, today_is_mon):
    """Kontrolle: eine geänderte Begründung ist eine neue Ausnahme (#144)."""
    _setting(_db_session, "break_exception_requires_approval", "true")
    e = _waived(_db_session, employee_user)
    r = employee_client.put(f"/api/time-entries/{e.id}",
                            json={**FORM, "note": "neu", "break_waiver_reason": "Notfall, Praxis voll"})
    assert r.status_code == 202, r.text
    _db_session.expire_all()
    e = _db_session.get(TimeEntry, e.id)
    assert (e.note, e.break_waiver_reason) == ("alt", "Notfall")
    assert _crs(_db_session, employee_user) == 1


def test_changed_break_with_same_reason_still_goes_through_approval(
        _db_session, employee_user, employee_client, today_is_mon):
    """Kontrolle: eine Pausenänderung ist eine Zeitänderung — §4 wie bisher."""
    _setting(_db_session, "break_exception_requires_approval", "true")
    e = _waived(_db_session, employee_user)
    r = employee_client.put(f"/api/time-entries/{e.id}",
                            json={**FORM, "break_minutes": 15, "note": "neu",
                                  "break_waiver_reason": "Notfall"})
    assert r.status_code == 202, r.text
    _db_session.expire_all()
    e = _db_session.get(TimeEntry, e.id)
    assert (e.break_minutes, e.note) == (0, "alt")
    assert _crs(_db_session, employee_user) == 1


def test_admin_route_same_reason_is_no_new_exception(_db_session, employee_user, admin_client):
    """Parallelpfad ``admin_update_time_entry``: dieselbe Regel — die gleiche,
    schon dokumentierte Begründung sperrt bei abgeschalteter Ausnahme nicht und
    wird nicht erneut als Ausnahme gemeldet."""
    _setting(_db_session, "break_exception_allowed", "false")
    e = _waived(_db_session, employee_user)
    r = admin_client.put(f"/api/admin/time-entries/{e.id}",
                         json={**FORM, "note": "neu", "break_waiver_reason": "Notfall"})
    assert r.status_code == 200, r.text
    assert not any(w.startswith("BREAK_WAIVER") for w in r.json()["warnings"])
    _db_session.refresh(e)
    assert (e.note, e.break_waiver_reason) == ("neu", "Notfall")


def test_admin_route_changed_reason_is_documented(_db_session, employee_user, admin_client):
    """Kontrolle: eine neue Begründung dokumentiert die Ausnahme wie bisher."""
    e = _waived(_db_session, employee_user)
    r = admin_client.put(f"/api/admin/time-entries/{e.id}",
                         json={**FORM, "note": "neu", "break_waiver_reason": "Notfall 2"})
    assert r.status_code == 200, r.text
    assert any(w.startswith("BREAK_WAIVER") for w in r.json()["warnings"])
    _db_session.refresh(e)
    assert e.break_waiver_reason == "Notfall 2"
