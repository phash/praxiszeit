"""Audit 2026-11-07, Lane B — ArbZG-Prüfungen an den Schreibpfaden (#538, #540).

A1-02 Überschneidungen · A1-04 Auto-Close mit §3/§4 und Spur · A1-05
Mindestlänge der §4-Begründung · A1-06 Genehmigungspflicht beim Ausstempeln
(siehe auch ``test_issue_499_break_chain``) · A1-09 Ende in der Zukunft /
Pause über die Spanne · A1-11 §10-Grund beim Ausstempeln, Warnung auf den
Verwaltungswegen · A2-7 Ausstempeln nach Mitternacht.
"""
from datetime import date, datetime, time, timedelta

import pytest

from app.models import ChangeRequest, ChangeRequestStatus, ChangeRequestType, TimeEntry, TimeEntryAuditLog
from app.services import entry_guard_service as g
from app.services.break_validation_service import (
    BREAK_WAIVER_MIN_LENGTH, BREAK_WAIVER_TOO_SHORT_HINT, break_waiver_rejection,
)
from tests.conftest import DEFAULT_TENANT_ID
from tests.entry_overlap_cases import MSG_CLOSED, MSG_RUNNING, O_CASES, hm
from tests.test_issue_499_break_chain import (  # noqa: F401 — Fixtures
    _entry, _freeze_now, _setting, admin, client_as, db, default_tenant, employee,
)

import app.routers.time_entries as te

DAY = date(2026, 6, 2)


# ── A1-02: Regel (Zwilling-Falltabelle) ───────────────────────────────────────

@pytest.mark.parametrize("case", O_CASES, ids=[c.id for c in O_CASES])
def test_overlap_rule_table(case):
    today = DAY + timedelta(days=1) if case.a_past_day else DAY
    now = hm(case.now)
    a = g.interval(hm(case.a[0]), hm(case.a[1]), on=DAY, today=today, now=now)
    if case.b[1] is None:  # Einstempeln: die Stempelminute
        b = g.interval(hm(case.b[0]), None, on=DAY, today=DAY, now=hm(case.b[0]))
    else:
        b = g.interval(hm(case.b[0]), hm(case.b[1]), on=DAY, today=today, now=now)
    assert g.overlaps(a, b) is case.overlap
    assert g.overlaps(b, a) is case.overlap


def test_overlap_messages_match_frontend():
    assert g.overlap_detail(g.Interval(480, 720), DAY) == MSG_CLOSED
    assert g.overlap_detail(g.Interval(480, 600, True), DAY) == MSG_RUNNING


def test_presence_uses_raw_stamps_and_auto_closed_effective_end():
    e = TimeEntry(date=DAY, start_time=time(7, 45), raw_start_time=time(7, 0),
                  end_time=time(18, 15), raw_end_time=time(23, 59), auto_closed=True)
    assert g.entry_interval(e, today=DAY, now=time(20)) == g.Interval(420, 1095, False)
    e.auto_closed = False
    assert g.entry_interval(e, today=DAY, now=time(20)) == g.Interval(420, 1439, False)


# ── A1-02: alle Schreibwege ───────────────────────────────────────────────────

def test_clock_in_inside_existing_entry_is_409(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 10, 10)
    _entry(db, employee, today, time(8), time(15))
    r = client_as(employee).post("/api/time-entries/clock-in", json={})
    assert r.status_code == 409, r.text
    assert r.json()["detail"].startswith("Überschneidung mit dem Eintrag 08:00–15:00")
    assert db.query(TimeEntry).count() == 1


def test_clock_in_right_after_entry_end_is_allowed(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 12, 0)
    _entry(db, employee, today, time(8), time(12))
    assert client_as(employee).post("/api/time-entries/clock-in", json={}).status_code == 201


def test_employee_create_overlapping_is_409_touching_is_201(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 20, 0)
    _entry(db, employee, today, time(8), time(12))
    c = client_as(employee)
    r = c.post("/api/time-entries/", json={
        "date": today.isoformat(), "start_time": "09:00", "end_time": "13:00", "break_minutes": 0})
    assert r.status_code == 409, r.text
    assert "08:00–12:00" in r.json()["detail"]
    r = c.post("/api/time-entries/", json={
        "date": today.isoformat(), "start_time": "12:00", "end_time": "13:00", "break_minutes": 0})
    assert r.status_code == 201, r.text


def test_employee_create_inside_running_entry_is_409(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 11, 0)
    _entry(db, employee, today, time(8), None)
    r = client_as(employee).post("/api/time-entries/", json={
        "date": today.isoformat(), "start_time": "09:00", "end_time": "10:00", "break_minutes": 0})
    assert r.status_code == 409, r.text
    assert "laufenden Eintrag ab 08:00" in r.json()["detail"]


def test_employee_update_into_overlap_is_409_note_on_legacy_overlap_ok(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 20, 0)
    _entry(db, employee, today, time(8), time(12))
    b = _entry(db, employee, today, time(13), time(15))
    c = client_as(employee)
    r = c.put(f"/api/time-entries/{b.id}", json={"start_time": "11:00", "end_time": "15:00"})
    assert r.status_code == 409, r.text
    db.rollback()
    # Bestand: eine schon bestehende Überschneidung bleibt bearbeitbar (Notiz).
    legacy = _entry(db, employee, today, time(9), time(10))
    r = c.put(f"/api/time-entries/{legacy.id}", json={"note": "geprüft"})
    assert r.status_code == 200, r.text


def test_admin_create_and_update_overlap_is_409(db, employee, admin, client_as, monkeypatch):
    _freeze_now(monkeypatch, 20, 0)
    _entry(db, employee, DAY, time(8), time(12))
    other = _entry(db, employee, DAY, time(13), time(14))
    c = client_as(admin)
    r = c.post(f"/api/admin/users/{employee.id}/time-entries", json={
        "date": DAY.isoformat(), "start_time": "11:30", "end_time": "12:30", "break_minutes": 0})
    assert r.status_code == 409, r.text
    r = c.put(f"/api/admin/time-entries/{other.id}", json={"start_time": "11:00"})
    assert r.status_code == 409, r.text
    db.rollback()
    db.expire_all()
    assert db.get(TimeEntry, other.id).start_time == time(13)


def test_change_request_submission_and_approval_check_overlap(db, employee, admin, client_as, monkeypatch):
    _freeze_now(monkeypatch, 20, 0)
    day = te._today_local() - timedelta(days=7)
    _entry(db, employee, day, time(8), time(12))
    r = client_as(employee).post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": day.isoformat(),
        "proposed_start_time": "11:00", "proposed_end_time": "13:00",
        "proposed_break_minutes": 0, "reason": "vergessen"})
    assert r.status_code == 409, r.text
    # Antrag ohne Überschneidung; danach entsteht ein kollidierender Eintrag →
    # die Genehmigung prüft erneut (vor der Statusänderung).
    r = client_as(employee).post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": day.isoformat(),
        "proposed_start_time": "13:00", "proposed_end_time": "15:00",
        "proposed_break_minutes": 0, "reason": "vergessen"})
    assert r.status_code in (200, 201), r.text
    cr_id = r.json()["id"]
    _entry(db, employee, day, time(14), time(16))
    r = client_as(admin).post(f"/api/admin/change-requests/{cr_id}/review", json={"action": "approve"})
    assert r.status_code == 409, r.text
    db.rollback()
    db.expire_all()
    assert db.get(ChangeRequest, cr_id).status == ChangeRequestStatus.PENDING


def test_clock_out_reports_but_does_not_block_overlap(db, employee, client_as, monkeypatch):
    """Ausstempeln sperrt nie (R2-b) — eine Bestands-Überschneidung wird gemeldet."""
    today = _freeze_now(monkeypatch, 12, 0)
    open_e = _entry(db, employee, today, time(8), None)
    _entry(db, employee, today, time(10), time(11))  # Bestand (vor der Sperre entstanden)
    r = client_as(employee).post("/api/time-entries/clock-out", json={"break_minutes": 0})
    assert r.status_code == 200, r.text
    assert any(w.startswith("ENTRY_OVERLAP: Überschneidung mit dem Eintrag 10:00–11:00")
               for w in r.json()["warnings"])
    db.expire_all()
    assert db.get(TimeEntry, open_e.id).end_time == time(12)


# ── A1-05: Mindestlänge der Begründung ────────────────────────────────────────

def test_waiver_min_length_rule(db, default_tenant):
    err = "§4"
    assert break_waiver_rejection(db, DEFAULT_TENANT_ID, err, "x") == f"{err} {BREAK_WAIVER_TOO_SHORT_HINT}"
    assert break_waiver_rejection(db, DEFAULT_TENANT_ID, err, "  " + "a" * (BREAK_WAIVER_MIN_LENGTH - 1) + "  ")
    assert break_waiver_rejection(db, DEFAULT_TENANT_ID, err, "a" * BREAK_WAIVER_MIN_LENGTH) is None
    assert break_waiver_rejection(db, DEFAULT_TENANT_ID, err, "") == err


def test_one_char_waiver_no_longer_lifts_break_block(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 20, 0)
    c = client_as(employee)
    body = {"date": today.isoformat(), "start_time": "08:00", "end_time": "15:00", "break_minutes": 0}
    r = c.post("/api/time-entries/", json={**body, "break_waiver_reason": "x"})
    assert r.status_code == 400, r.text
    assert "mindestens 10 Zeichen" in r.json()["detail"] and "Pause" in r.json()["detail"]
    r = c.post("/api/time-entries/", json={**body, "break_waiver_reason": "Notfall im Wartezimmer"})
    assert r.status_code == 201, r.text


def test_short_waiver_at_clock_out_keeps_entry_open(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 15, 0)
    open_e = _entry(db, employee, today, time(8), None)
    r = client_as(employee).post("/api/time-entries/clock-out", json={
        "break_minutes": 0, "break_waiver_reason": "Notfall"})
    assert r.status_code == 400, r.text
    db.rollback()
    db.expire_all()
    assert db.get(TimeEntry, open_e.id).end_time is None


# ── A1-06: genehmigter Ausstempel-Antrag ──────────────────────────────────────

def test_clock_out_waiver_request_approval_materialises_reason(db, employee, admin, client_as, monkeypatch):
    _setting(db, "break_exception_requires_approval", "true")
    today = _freeze_now(monkeypatch, 15, 0)
    open_e = _entry(db, employee, today, time(8), None)
    r = client_as(employee).post("/api/time-entries/clock-out", json={
        "break_minutes": 0, "break_waiver_reason": "Notfall ohne Vertretung"})
    assert r.status_code == 200, r.text
    cr = db.query(ChangeRequest).one()
    r = client_as(admin).post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    db.expire_all()
    e = db.get(TimeEntry, open_e.id)
    assert (e.start_time, e.end_time, e.break_waiver_reason) == (time(8), time(15), "Notfall ohne Vertretung")
    assert db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.time_entry_id == e.id, TimeEntryAuditLog.source == "break_waiver").count() == 1


# ── A1-04 / A2-7: Auto-Close ──────────────────────────────────────────────────

def test_auto_close_reports_s3_s4_and_leaves_trace(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 7, 30)
    stale = _entry(db, employee, today - timedelta(days=1), time(8), None)
    r = client_as(employee).post("/api/time-entries/clock-in", json={})
    assert r.status_code == 201, r.text
    notice = next(w for w in r.json()["warnings"] if w.startswith("AUTO_CLOSED:"))
    assert "§ 3 ArbZG" in notice and "§ 4 ArbZG" in notice and "Änderungsantrag" in notice
    db.expire_all()
    e = db.get(TimeEntry, stale.id)
    assert (e.end_time, e.auto_closed) == (time(23, 59), True)
    assert e.note.startswith("[auto-closed] Nicht ausgestempelt") and "§ 3 ArbZG" in e.note
    audit = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.time_entry_id == e.id, TimeEntryAuditLog.source == "auto_close").one()
    assert "§ 4 ArbZG" in audit.new_note


def test_auto_close_without_violation_has_no_findings(db, employee, client_as, monkeypatch):
    employee.exempt_from_arbzg = True
    db.commit()
    today = _freeze_now(monkeypatch, 7, 30)
    _entry(db, employee, today - timedelta(days=1), time(8), None)
    r = client_as(employee).post("/api/time-entries/clock-in", json={})
    notice = next(w for w in r.json()["warnings"] if w.startswith("AUTO_CLOSED:"))
    assert "Prüfung" not in notice


def test_stale_clock_out_keeps_attempt_and_offers_request(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 6, 12)
    stale = _entry(db, employee, today - timedelta(days=1), time(22), None)
    c = client_as(employee)
    r = c.post("/api/time-entries/clock-out", json={"break_minutes": 0})
    assert r.status_code == 200, r.text
    assert r.json()["auto_closed"] is True
    db.expire_all()
    e = db.get(TimeEntry, stale.id)
    assert f"Ausstempelversuch am {today.strftime('%d.%m.%Y')} um 06:12" in e.note
    # Die Stempeluhr bietet den Antrag an …
    status = c.get("/api/time-entries/clock-status").json()
    assert [x["id"] for x in status["auto_closed_entries"]] == [str(e.id)]
    assert status["auto_closed_entries"][0]["warnings"][0].startswith("AUTO_CLOSED:")
    # … bis ein Antrag läuft.
    db.add(ChangeRequest(
        user_id=employee.id, tenant_id=DEFAULT_TENANT_ID, request_type=ChangeRequestType.UPDATE,
        entry_kind="time_entry", status=ChangeRequestStatus.PENDING, time_entry_id=e.id,
        proposed_date=e.date, proposed_start_time=time(22), proposed_end_time=time(23, 30),
        proposed_break_minutes=0, reason="Ende nachgetragen"))
    db.commit()
    assert c.get("/api/time-entries/clock-status").json()["auto_closed_entries"] == []


def test_admin_list_of_uncorrected_auto_closed_entries(db, employee, admin, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 7, 30)
    stale = _entry(db, employee, today - timedelta(days=1), time(8), None)
    te._close_stale_entry(db, stale)
    db.commit()
    rows = client_as(admin).get("/api/admin/time-entries/auto-closed").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == str(stale.id) and row["user_name"] == "Vor emp499"
    assert any("§ 3 ArbZG" in f for f in row["findings"]) and row["pending_change_request"] is False
    # Korrigiert (tatsächliches Ende) → nicht mehr in der Liste.
    r = client_as(admin).put(f"/api/admin/time-entries/{stale.id}", json={"end_time": "16:00", "break_minutes": 30})
    assert r.status_code == 200, r.text
    assert client_as(admin).get("/api/admin/time-entries/auto-closed").json() == []


# ── A1-09: Ende in der Zukunft, Pause über die Spanne ─────────────────────────

def test_future_end_today_is_rejected(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 10, 12)
    c = client_as(employee)
    r = c.post("/api/time-entries/", json={
        "date": today.isoformat(), "start_time": "08:00", "end_time": "10:30", "break_minutes": 0})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == g.FUTURE_END_DETAIL
    r = c.post("/api/time-entries/", json={
        "date": today.isoformat(), "start_time": "08:00", "end_time": "10:12", "break_minutes": 0})
    assert r.status_code == 201, r.text
    r = c.put(f"/api/time-entries/{r.json()['id']}", json={"end_time": "11:00"})
    assert r.status_code == 400, r.text


def test_admin_future_end_today_is_rejected(db, employee, admin, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 10, 0)
    r = client_as(admin).post(f"/api/admin/users/{employee.id}/time-entries", json={
        "date": today.isoformat(), "start_time": "08:00", "end_time": "17:00", "break_minutes": 30})
    assert r.status_code == 400, r.text


def test_break_as_long_as_the_entry_is_rejected(db, employee, admin, client_as, monkeypatch):
    _freeze_now(monkeypatch, 20, 0)
    r = client_as(admin).post(f"/api/admin/users/{employee.id}/time-entries", json={
        "date": DAY.isoformat(), "start_time": "08:00", "end_time": "09:00", "break_minutes": 60})
    assert r.status_code == 400, r.text
    assert "Pause (60 Min.)" in r.json()["detail"]
    today = te._today_local()
    open_e = _entry(db, employee, today, time(19, 30), None)
    r = client_as(employee).post("/api/time-entries/clock-out", json={"break_minutes": 30})
    assert r.status_code == 400, r.text
    db.rollback()
    db.expire_all()
    assert db.get(TimeEntry, open_e.id).end_time is None


# ── A1-11: §10 beim Ausstempeln, Verwaltungswege ──────────────────────────────

def test_clock_out_stores_sunday_reason(db, employee, client_as, monkeypatch):
    today = _freeze_now(monkeypatch, 12, 0)
    open_e = _entry(db, employee, today, time(9), None)
    r = client_as(employee).post("/api/time-entries/clock-out", json={
        "break_minutes": 0, "sunday_exception_reason": "  Notdienst  "})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(TimeEntry, open_e.id).sunday_exception_reason == "Notdienst"


def test_admin_create_on_sunday_warns(db, employee, admin, client_as, monkeypatch):
    _freeze_now(monkeypatch, 20, 0)
    sunday = date(2026, 6, 7)
    c = client_as(admin)
    r = c.post(f"/api/admin/users/{employee.id}/time-entries", json={
        "date": sunday.isoformat(), "start_time": "09:00", "end_time": "12:00", "break_minutes": 0})
    assert r.status_code == 201, r.text
    assert any(w.startswith("SUNDAY_WORK:") and "Ausnahmegrund" in w for w in r.json()["warnings"])
    r = c.post(f"/api/admin/users/{employee.id}/time-entries", json={
        "date": sunday.isoformat(), "start_time": "13:00", "end_time": "14:00", "break_minutes": 0,
        "sunday_exception_reason": "Notdienst"})
    assert [w for w in r.json()["warnings"] if w.startswith("SUNDAY_WORK:")] == [
        "SUNDAY_WORK: Sonntagsarbeit eingetragen (§9 ArbZG)."]


# ── A1-10: §5-Warnung beim Einstempeln über die Zeitumstellung ────────────────

def test_clock_in_rest_warning_counts_real_hours_over_dst(db, employee, client_as, monkeypatch):
    sunday = date(2026, 3, 29)
    monkeypatch.setattr(te, "_today_local", lambda: sunday)
    monkeypatch.setattr(te, "_now_local", lambda: datetime(2026, 3, 29, 7, 0, tzinfo=te.LOCAL_TZ))
    _entry(db, employee, date(2026, 3, 28), time(12), time(20))
    r = client_as(employee).post("/api/time-entries/clock-in", json={})
    assert r.status_code == 201, r.text
    rest = [w for w in r.json()["warnings"] if w.startswith("REST_TIME_WARNING")]
    assert rest and "Nur 10.0h" in rest[0], r.json()["warnings"]
