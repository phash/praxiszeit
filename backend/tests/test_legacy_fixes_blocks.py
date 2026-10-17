"""Spec 7.2 / 2.7: E39, E40, E41 — und P3 (409), P28."""
import datetime as dt
from datetime import date, time

import pytest

from app.models import ChangeRequest, SystemSetting, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week, legacy_week

import app.routers.time_entries as te

FRI_BEFORE = date(2026, 5, 29)


def _entry(db, user, d, start, end, brk=0, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=brk, **kw)
    db.add(e)
    db.commit()
    return e


def test_e39_date_change_reclamps_and_warns(_db_session, employee_user, admin_client, monkeypatch):
    """E39 über ``update_time_entry`` (``PUT /api/time-entries/{id}``): seit
    #502 wechselt dort nur noch die Verwaltung das Datum eines Eintrags —
    Mitarbeitende bleiben auf heute → heute (Test darunter). Die Neukappung
    gegen die Blöcke des neuen Tages und die Warnung gelten unverändert."""
    employee_user.work_blocks = legacy_week(fri=("08:00", "17:00"))
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(7, 0), time(16, 0), 30)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={"date": FRI_BEFORE.isoformat()})
    assert resp.status_code == 200, resp.text
    assert any(w.startswith("WORK_WINDOW_CLAMPED") for w in resp.json()["warnings"])
    _db_session.refresh(e)
    assert (e.date, e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (FRI_BEFORE, time(7, 45), time(7, 0), 15)


def test_e39_employee_date_change_rejected(_db_session, employee_user, employee_client, monkeypatch):
    """#502 (Entschieden 2026-10-10): der MA-Datumswechsel weg von heute ist
    gesperrt — Einträge vergangener Tage nur per Änderungsantrag. Vorher
    verschob genau dieser PUT den heutigen Eintrag in die Vergangenheit."""
    employee_user.work_blocks = legacy_week(fri=("08:00", "17:00"))
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(7, 0), time(16, 0), 30)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"date": FRI_BEFORE.isoformat()})
    assert resp.status_code == 403, resp.text
    _db_session.refresh(e)
    assert (e.date, e.start_time, e.raw_start_time) == (MON, time(7, 0), None)


def test_e39_date_change_reclamps_end_too(_db_session, employee_user, admin_client, monkeypatch):
    """Review Task 9: auch das Ende gehört zum alten Tag. Am Montag (ohne
    Blöcke) ungekappt 07:00–17:30, am Freitag (Hülle 07:45–17:15) gekappt —
    ohne ``date`` im Ende-Gate bliebe 17:30 als angerechnete Zeit stehen.
    Seit #502 über die Verwaltung (siehe oben)."""
    employee_user.work_blocks = legacy_week(fri=("08:00", "17:00"))
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(7, 0), time(17, 30), 45)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 18, 0))
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={"date": FRI_BEFORE.isoformat()})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.start_time, e.raw_start_time, e.end_time, e.raw_end_time) == (
        time(7, 45), time(7, 0), time(17, 15), time(17, 30))


def test_e40_request_validates_on_credited_time_and_stores_raw(_db_session, employee_user, employee_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "18:00",
        "proposed_break_minutes": 0, "reason": "Nachtrag Teilschicht"})
    assert resp.status_code == 201, resp.text
    cr = _db_session.query(ChangeRequest).one()
    assert (cr.proposed_start_time, cr.proposed_end_time) == (time(8, 0), time(18, 0))


def test_e40_daily_cap_counts_credited_time(_db_session, employee_user, employee_client):
    """Review Task 9: die §3-Tagesgrenze (hart, 422) rechnet ebenfalls auf der
    angerechneten Zeit. 07:00–18:30 ohne Pause: roh 11,5 h, gekappt auf die
    Hülle 07:45–18:15 noch 10,5 h, abzüglich 150 Min Lücke 8,0 h → zulässig.
    Gespeichert bleiben die rohen Vorschläge."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": MON.isoformat(),
        "proposed_start_time": "07:00", "proposed_end_time": "18:30",
        "proposed_break_minutes": 0, "reason": "Nachtrag"})
    assert resp.status_code == 201, resp.text
    cr = _db_session.query(ChangeRequest).one()
    assert (cr.proposed_start_time, cr.proposed_end_time) == (time(7, 0), time(18, 30))


# Review Task 9: die beiden Tests oben decken nur den Teil VOR dem Speichern
# (§4-Lückensegmente, §3-Tagesgrenze). Die Hinweise NACH dem Speichern (§6
# Nachtarbeitnehmer, 48-h-Woche) rechnen ebenfalls auf der angerechneten Zeit.
# Je Fall eine Kontrolle ohne Lücke bzw. ohne Kappung: sie warnt, damit der
# Negativfall nicht still grün bleibt, falls die Warnung gar nicht mehr feuert.
@pytest.mark.parametrize("fri_blocks, warned", [
    ([("08:00", "12:00"), ("15:00", "18:00")], False),  # Lücke 12:15–14:45
    ([("08:00", "18:00")], True),                         # Kontrolle ohne Lücke
])
def test_e40_request_weekly_warning_uses_credited_time(
        _db_session, employee_user, employee_client, fri_blocks, warned):
    """Mo–Do je 10,0 h = 40 h; Fr-Antrag 08:00–18:00, Pause 45: roh 9,25 h
    (Woche 49,25 h → Warnung), angerechnet 6,75 h (46,75 h → keine)."""
    employee_user.work_blocks = block_week(fri=fri_blocks)
    _db_session.commit()
    for day in range(1, 5):
        _entry(_db_session, employee_user, date(2026, 6, day), time(7), time(17, 15), 15)
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": "2026-06-05",
        "proposed_start_time": "08:00", "proposed_end_time": "18:00",
        "proposed_break_minutes": 45, "reason": "Nachtrag"})
    assert resp.status_code == 201, resp.text
    assert ("WEEKLY_HOURS_WARNING" in resp.json()["warnings"]) is warned, resp.json()["warnings"]


@pytest.mark.parametrize("mon_blocks, start, end, warned", [
    # Tageswert: 00:30–10:00, Pause 45 → roh 8,75 h; Lücke 04:15–06:45 →
    # angerechnet 6,25 h. Nachtarbeit liegt in beiden Fällen vor.
    ([("00:30", "04:00"), ("07:00", "10:00")], "00:30", "10:00", False),
    ([("00:30", "10:00")], "00:30", "10:00", True),
    # Einstufung: 03:00–13:30, Pause 45 → roh 180 Min Nachtzeit; gekappt ab
    # 04:00 nur 120 Min (nicht mehr als 2 h, § 2 Abs. 4) bei angerechneten
    # 8,75 h > 8 h — hier schweigt allein die Nachtarbeits-Einstufung.
    ([("04:15", "13:30")], "03:00", "13:30", False),
    ([("03:15", "13:30")], "03:00", "13:30", True),
])
def test_e40_request_night_worker_warning_uses_credited_time(
        _db_session, employee_user, employee_client, mon_blocks, start, end, warned):
    employee_user.is_night_worker = True
    employee_user.work_blocks = block_week(mon=mon_blocks)
    _db_session.commit()
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": MON.isoformat(),
        "proposed_start_time": start, "proposed_end_time": end,
        "proposed_break_minutes": 45, "reason": "Nachtrag"})
    assert resp.status_code == 201, resp.text
    night = [w for w in resp.json()["warnings"] if w.startswith("§6 ArbZG")]
    assert bool(night) is warned, resp.json()["warnings"]


def test_p28_request_snapshots_uncredited(_db_session, employee_user, employee_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(8), time(18), 45,
               uncredited_minutes=150, clamp_grace_minutes=15)
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id), "proposed_date": MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "18:00",
        "proposed_break_minutes": 45, "reason": "Notiz"})
    assert resp.status_code == 201, resp.text
    assert _db_session.query(ChangeRequest).one().original_uncredited_minutes == 150


def test_p28_waiver_request_snapshots_uncredited(_db_session, employee_user, employee_client, monkeypatch):
    """Review Task 9: auch der Waiver-Antrag des MA-PUT (Pausenausnahme mit
    Genehmigungspflicht) hält den Vorher-Stand der Lückenminuten fest."""
    _db_session.add(SystemSetting(key="break_exception_requires_approval",
                                  tenant_id=DEFAULT_TENANT_ID, value="true"))
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(8), time(18), 45, uncredited_minutes=150)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 19, 0))
    resp = employee_client.put(f"/api/time-entries/{e.id}",
                               json={"break_minutes": 0, "break_waiver_reason": "Notfall"})
    assert resp.status_code == 202, resp.text
    assert _db_session.query(ChangeRequest).one().original_uncredited_minutes == 150


def test_e41_post_commit_check_counts_entry_once(_db_session, employee_user, admin_client):
    for day in range(1, 5):                                  # Mo–Do je 9,5 h = 38 h
        _entry(_db_session, employee_user, date(2026, 6, day), time(7), time(17, 15), 45)
    fri = _entry(_db_session, employee_user, date(2026, 6, 5), time(8), time(14))   # 6 h → 44 h
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=fri.id, proposed_date=date(2026, 6, 5),
                       proposed_start_time=time(8), proposed_end_time=time(14),
                       proposed_break_minutes=0, proposed_note="Nachtrag", reason="Notiz")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    assert not [w for w in resp.json()["warnings"] if "Wochenarbeitszeit" in w], resp.json()["warnings"]


# Review Task 9: der Test oben hält nur fest, dass der Eintrag NICHT doppelt
# zählt. Die beiden folgenden halten fest, dass er GENAU EINMAL zählt und dabei
# mit seiner ANGERECHNETEN Zeit (Spec 7.1 Nr. 10 — die in Review Task 4 auf
# E41 verschobene Aufrufstelle). Mo–Do je 10,0 h (07:00–17:15, Pause 15) = 40 h.
def _seed_week_and_approve_fri(db, user, client, start, end, brk):
    for day in range(1, 5):
        _entry(db, user, date(2026, 6, day), time(7), time(17, 15), 15)
    fri = _entry(db, user, date(2026, 6, 5), time(8), time(12))
    cr = ChangeRequest(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=fri.id, proposed_date=date(2026, 6, 5),
                       proposed_start_time=start, proposed_end_time=end,
                       proposed_break_minutes=brk, reason="Notiz")
    db.add(cr)
    db.commit()
    resp = client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    return [w for w in resp.json()["warnings"] if "Wochenarbeitszeit" in w]


def test_e41_entry_counts_exactly_once(_db_session, employee_user, admin_client):
    """Fr 08:00–17:00, Pause 45 → 8,25 h → Woche 48,25 h. Einmal gezählt warnt
    es mit genau diesem Wert; gar nicht gezählt (40 h) schwiege die Warnung,
    doppelt gezählt (56,5 h) nennte sie einen anderen Wert."""
    warnings = _seed_week_and_approve_fri(_db_session, employee_user, admin_client, time(8), time(17), 45)
    assert warnings == ["§3 ArbZG: Wochenarbeitszeit 48.2h überschreitet 48h-Grenze."], warnings


def test_e41_post_commit_uses_credited_time(_db_session, employee_user, admin_client):
    """Fr mit Lücke 12:15–14:45: 08:00–18:00, Pause 45 → roh 9,25 h (Woche
    49,25 h → Warnung), angerechnet 6,75 h (Woche 46,75 h → keine)."""
    employee_user.work_blocks = block_week(fri=[("08:00", "12:00"), ("15:00", "18:00")])
    _db_session.commit()
    assert _seed_week_and_approve_fri(_db_session, employee_user, admin_client, time(8), time(18), 45) == []


def test_p3_employee_put_on_acknowledged_entry_is_409(_db_session, employee_user, employee_client, monkeypatch):
    e = _entry(_db_session, employee_user, MON, time(8), time(12), credit_override=True)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"note": "x"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Anerkannter Eintrag – Änderung bitte per Änderungsantrag."


def test_p3_admin_on_the_employee_route_keeps_the_flag(_db_session, employee_user, admin_client):
    """P3 nennt „MA-PUT": die Verwaltung bestätigt neue Zeiten ausdrücklich —
    auch wenn sie den Mitarbeiter-Endpunkt benutzt (TimeTracking-Seite)."""
    employee_user.work_blocks = legacy_week(mon=("08:00", "12:00"))  # ohne Anerkennung: Ende → 12:15
    e = _entry(_db_session, employee_user, MON, time(7), time(12), credit_override=True)
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={"end_time": "12:30"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.credit_override) == (time(12, 30), None, True)


def test_employee_put_ignores_server_side_fields(_db_session, employee_user, employee_client, monkeypatch):
    """Spec 7.1 Nr. 4/E11: uncredited_minutes, credit_override, auto_closed,
    clamp_grace_minutes nie über die generische setattr-Schleife."""
    e = _entry(_db_session, employee_user, MON, time(8), time(12))
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={
        "note": "x", "uncredited_minutes": 999, "credit_override": True,
        "auto_closed": True, "clamp_grace_minutes": 99})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.uncredited_minutes, e.credit_override, e.auto_closed, e.clamp_grace_minutes) == (0, False, False, None)


def test_p3_admin_edit_and_cr_update_keep_flag(_db_session, employee_user, admin_client):
    e = _entry(_db_session, employee_user, MON, time(8), time(12), credit_override=True)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "12:30"}).status_code == 200
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=e.id, proposed_date=MON, proposed_start_time=time(8),
                       proposed_end_time=time(13), proposed_break_minutes=0, reason="Notiz")
    _db_session.add(cr)
    _db_session.commit()
    assert admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"}).status_code == 200
    _db_session.refresh(e)
    assert (e.end_time, e.credit_override) == (time(13), True)
