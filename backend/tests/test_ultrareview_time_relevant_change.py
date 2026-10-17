"""Ultrareview 1.20 (Fund B): EINE Regel „nichts §3/§4-Relevantes geändert".

Die Prüfung, ob eine Bearbeitung die HARTEN §3/§4-Prüfungen auslöst (Gesamtreview
1.20 B1), stand viermal handgeschrieben da — beide Bearbeiten-Routen, Stellen und
Genehmigung des Änderungsantrags — mit kleinen Unterschieden:

* Antrag (Stellen + Genehmigung) normalisierte eine fehlende Pause als 0
  (``proposed_break_minutes or 0``), die Genehmigung SCHREIBT aber die
  gespeicherte Pause weiter. Ein Antrag ohne Pause an einem Eintrag mit Pause
  galt damit als Pausenänderung (harte Prüfungen liefen), und geprüft wurde mit
  0 Minuten Pause statt mit der, die gespeichert wird.
* Die Verwaltungsroute verglich die NEU gekappten Zeiten, auch wenn sie sie gar
  nicht schreibt (reine Notiz ohne Datum/Zeit) — die MA-Route vergleicht, was
  gespeichert wird. Ein Eintrag, dessen gespeicherte Kappung nicht mehr zum
  Snapshot passt, scheiterte so an der Notiz.

Sollregel (CLAUDE.md, §4 ArbZG #499): eine Bearbeitung ohne Änderung an Datum,
angerechnetem Beginn/Ende, Pause oder ``uncredited_minutes`` scheitert nicht an
hartem §3/§4 — gemessen am Stand, der gespeichert wird.
"""
from datetime import date, time

import pytest

from app.middleware.auth import get_current_user, require_admin
from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.services import work_window_service
from app.services.work_window_service import effective_break_minutes, time_relevant_change
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
    endpoints_app,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

D = date(2026, 6, 1)
BEFORE = dict(date=D, start_time=time(8), end_time=time(17), break_minutes=30,
              uncredited_minutes=10)
SAME = dict(date=D, start=time(8), end=time(17), break_minutes=30, uncredited_minutes=10)


# ── Helfer ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("change, expected", [
    ({}, False),                                          # nur Notiz / unverändert
    ({"break_minutes": None}, False),                     # Pause fehlt = bleibt
    ({"break_minutes": 0}, True),                         # Pause auf 0 gesetzt
    ({"break_minutes": 45}, True),
    ({"date": date(2026, 6, 2)}, True),
    ({"start": time(7, 45)}, True),                       # angerechneter Beginn
    ({"end": time(17, 15)}, True),                        # angerechnetes Ende
    ({"end": None}, True),
    ({"uncredited_minutes": 0}, True),
    ({"uncredited_minutes": None}, True),                 # None = 0 Minuten
], ids=["unchanged", "break-none", "break-0", "break-45", "date", "start", "end",
        "end-none", "uncredited", "uncredited-none"])
@pytest.mark.parametrize("as_dict", [True, False], ids=["dict", "object"])
def test_helper_table(change, expected, as_dict):
    before = BEFORE if as_dict else TimeEntry(**BEFORE)
    assert time_relevant_change(before, **{**SAME, **change}) is expected


def test_helper_stored_break_none_equals_zero():
    before = {**BEFORE, "break_minutes": None}
    assert time_relevant_change(before, **{**SAME, "break_minutes": 0}) is False
    assert time_relevant_change(before, **{**SAME, "break_minutes": None}) is False


def test_helper_new_entry_is_always_a_change():
    assert time_relevant_change(None, **SAME) is True


def test_effective_break_minutes():
    assert effective_break_minutes(None, BEFORE) == 30
    assert effective_break_minutes(None, TimeEntry(**BEFORE)) == 30
    assert effective_break_minutes(0, BEFORE) == 0
    assert effective_break_minutes(None, None) == 0
    assert effective_break_minutes(15, None) == 15


# ── Jede Route nutzt den Helfer ─────────────────────────────────────────────

@pytest.fixture
def helper_calls(monkeypatch):
    calls = []
    real = work_window_service.time_relevant_change

    def spy(before, **kw):
        result = real(before, **kw)
        calls.append(result)
        return result

    monkeypatch.setattr(work_window_service, "time_relevant_change", spy)
    return calls


def _entry(db, user, start, end, *, brk=0, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=kw.pop("day", MON),
                  start_time=start, end_time=end, break_minutes=brk,
                  uncredited_minutes=kw.pop("uncredited_minutes", 0),
                  clamp_grace_minutes=15, note="alt", **kw)
    db.add(e)
    db.commit()
    return e


def _cr(db, user, entry, **kw):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
        time_entry_id=entry.id, proposed_date=entry.date,
        proposed_start_time=kw.pop("start", entry.start_time),
        proposed_end_time=kw.pop("end", entry.end_time),
        proposed_break_minutes=kw.pop("break_minutes", None),
        proposed_note="Hausbesuch", reason="Notiz ergänzt",
        original_date=entry.date, original_start_time=entry.start_time,
        original_end_time=entry.end_time, original_break_minutes=entry.break_minutes,
        original_note=entry.note, original_uncredited_minutes=entry.uncredited_minutes, **kw)
    db.add(cr)
    db.commit()
    return cr


def _switch_to(admin):
    endpoints_app.dependency_overrides[get_current_user] = lambda: admin
    endpoints_app.dependency_overrides[require_admin] = lambda: admin


@pytest.mark.parametrize("route", ["/api/admin/time-entries", "/api/time-entries"],
                         ids=["admin-route", "ma-route"])
def test_edit_routes_use_the_helper(_db_session, admin_user, admin_client, helper_calls, route):
    e = _entry(_db_session, admin_user, time(8), time(16), brk=30)
    r = admin_client.put(f"{route}/{e.id}", json={"note": "geprüft"})
    assert r.status_code == 200, r.text
    assert helper_calls == [False]


def test_request_create_uses_the_helper(_db_session, employee_user, employee_client,
                                        helper_calls):
    e = _entry(_db_session, employee_user, time(8), time(16), brk=30)
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id),
        "proposed_date": MON.isoformat(), "proposed_start_time": "08:00",
        "proposed_end_time": "16:00", "proposed_break_minutes": 30,
        "proposed_note": "x", "reason": "Notiz"})
    assert r.status_code == 201, r.text
    assert helper_calls == [False]


def test_request_approval_uses_the_helper(_db_session, employee_user, admin_client,
                                          helper_calls):
    e = _entry(_db_session, employee_user, time(8), time(16), brk=30)
    cr = _cr(_db_session, employee_user, e, break_minutes=30)
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert helper_calls == [False]


# ── Abweichung 1: Antrag ohne Pause ─────────────────────────────────────────

def _recognized_with_break(db, user):
    """Anerkannt 07:00–19:00 mit 60 Min. Pause: 11 h netto (§3)."""
    user.work_blocks = K_BLOCKS
    return _entry(db, user, time(7), time(19), brk=60, credit_override=True)


def test_note_only_request_without_break_is_accepted(_db_session, employee_user,
                                                     employee_client):
    """Fehlt die Pause im Antrag, bleibt sie stehen — keine Pausenänderung."""
    e = _recognized_with_break(_db_session, employee_user)
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id),
        "proposed_date": MON.isoformat(), "proposed_start_time": "07:00",
        "proposed_end_time": "19:00", "proposed_note": "Hausbesuch", "reason": "Notiz"})
    assert r.status_code == 201, r.text


def test_approving_a_note_only_request_without_break(_db_session, employee_user,
                                                     admin_client):
    e = _recognized_with_break(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e)
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.break_minutes, e.note, e.credit_override) == (60, "Hausbesuch", True)


def test_request_without_break_is_checked_with_the_stored_break(_db_session, employee_user,
                                                                employee_client, admin_user):
    """Geprüft wird die Pause, die gespeichert wird: 08:00–16:30 mit den
    gespeicherten 30 Min. = 8 h — kein §4-Verstoss (mit 0 Min. wären es 8,5 h
    ohne Pause)."""
    e = _entry(_db_session, employee_user, time(8), time(16), brk=30)
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id),
        "proposed_date": MON.isoformat(), "proposed_start_time": "08:00",
        "proposed_end_time": "16:30", "reason": "später gegangen"})
    assert r.status_code == 201, r.text
    cr = _db_session.query(ChangeRequest).one()
    assert cr.break_waiver_reason is None
    _switch_to(admin_user)
    r = employee_client.post(f"/api/admin/change-requests/{cr.id}/review",
                             json={"action": "approve"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.end_time, e.break_minutes) == (time(16, 30), 30)


def test_request_without_break_still_checked_hard_on_time_change(_db_session, employee_user,
                                                                 employee_client):
    """Kontrolle: 07:00–19:30 mit den gespeicherten 60 Min. = 11,5 h > 10 h (§3).
    Vorher rechnete das Stellen mit 0 Min. und scheiterte schon an §4 (400)."""
    e = _recognized_with_break(_db_session, employee_user)
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id),
        "proposed_date": MON.isoformat(), "proposed_start_time": "07:00",
        "proposed_end_time": "19:30", "reason": "länger"})
    assert r.status_code == 422, r.text


# ── Abweichung 2: Verwaltungsroute, reine Notiz an veralteter Kappung ───────

def _stale(db, user):
    """Gespeichert 05:00–17:00 (12 h) ohne Rohstempel, der Snapshot kappt heute
    auf 05:45 (Block 06:00–20:00, Puffer 15) → 11,25 h. Die Notiz schreibt die
    Zeiten nicht — der gespeicherte Stand bleibt, wie er ist."""
    user.work_blocks = legacy_week(mon=("06:00", "20:00"))
    return _entry(db, user, time(5), time(17), brk=0)


@pytest.mark.parametrize("route", ["/api/admin/time-entries", "/api/time-entries"],
                         ids=["admin-route", "ma-route"])
def test_note_only_edit_of_a_stale_clamp(_db_session, admin_user, admin_client, route):
    e = _stale(_db_session, admin_user)
    r = admin_client.put(f"{route}/{e.id}", json={"note": "geprüft"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.start_time, e.end_time, e.note) == (time(5), time(17), "geprüft")


@pytest.mark.parametrize("route", ["/api/admin/time-entries", "/api/time-entries"],
                         ids=["admin-route", "ma-route"])
def test_stale_clamp_is_checked_when_the_times_are_written(_db_session, admin_user,
                                                           admin_client, route):
    """Kontrolle: schickt das Formular Datum und Zeiten mit, wird neu gekappt und
    geschrieben (05:45–17:00 = 11,25 h ohne Pause) — das ist eine Änderung, hart
    geprüft (Verwaltungsroute §4 zuerst → 400, MA-Route §3 zuerst → 422)."""
    e = _stale(_db_session, admin_user)
    r = admin_client.put(f"{route}/{e.id}", json={
        "date": MON.isoformat(), "start_time": "05:00", "end_time": "17:00",
        "break_minutes": 0, "note": "geprüft"})
    assert r.status_code in (400, 422), r.text
