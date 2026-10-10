"""Sicherheitsfund F1 (P18/E42): ein automatisch geschlossener Eintrag, der nur
im DATUM verschoben wird, rechnet am Zieltag nicht bis 23:59 an.

Ausgangslage (K_BLOCKS, Montag): eingestempelt 15:00, nicht ausgestempelt, der
Auto-Close kappt 23:59 auf die Hülle → wirksames Ende 18:15, Rohende 23:59
(synthetisch, P18), 3,25 h angerechnet. Das Formular schickt das wirksame Ende
18:15 mit. Bis zum Fix stellte ``unclamp_input`` daraus das Rohende 23:59
wieder her — am Zieltag ohne Blöcke (Samstag, Feiertag) blieb es ungekappt
(15:00–23:59 ≈ 9 h), an einem Tag mit späterer Hülle wurde bis zu ihr
angerechnet. 23:59 ist dort kein Stempel; die Eingabe ist das gespeicherte
wirksame Ende (``work_window_service.end_input_for``).

Gleiches Datum = Kontrollfall: unverändertes Verhalten nach P18 (Rohende 23:59
weiter als Kappungseingabe, Hülle 18:15, Kennzeichen bleibt).

Je Pfad: MA-Antrag (E40, nur Prüfung), Antragsgenehmigung UPDATE (Vorprüfung +
Schreiben), Admin-Bearbeitung (``/api/admin/time-entries``) und die
Bearbeiten-Route der Beschäftigten, über die Admins fremde Einträge verschieben.
"""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.public_holiday import PublicHoliday
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_cases import EASTER_MONDAY
from tests.work_blocks_fixtures import MON, block_week

import app.routers.time_entries as te

SAT = date(2026, 6, 6)    # Samstag — keine Blöcke
WED = date(2026, 6, 3)    # Mittwoch — Block bis 20:00, Hülle bis 20:15
# Montag wie K_BLOCKS (Hülle 07:45–18:15), Mittwoch mit späterer Hülle.
WEEK = block_week(
    mon=[("08:00", "12:00"), ("15:00", "18:00")],
    wed=[("08:00", "20:00")],
)


@pytest.fixture
def auto_closed_entry(_db_session, employee_user):
    employee_user.work_blocks = WEEK
    _db_session.add(PublicHoliday(date=EASTER_MONDAY, name="Ostermontag", year=2026,
                                  tenant_id=DEFAULT_TENANT_ID))
    _db_session.commit()
    invalidate_holiday_cache()
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                  start_time=time(15, 0), end_time=None, break_minutes=0)
    _db_session.add(e)
    _db_session.commit()
    te._close_stale_entry(_db_session, e)
    _db_session.commit()
    assert (e.end_time, e.raw_end_time, e.auto_closed, e.net_hours) == (
        time(18, 15), time(23, 59), True, Decimal("3.25"))
    yield e
    invalidate_holiday_cache()


# Zieltag → (wirksames Ende, Rohende) nach dem Verschieben.
_MOVED = [
    pytest.param(SAT, (time(18, 15), None), id="samstag"),
    pytest.param(EASTER_MONDAY, (time(18, 15), None), id="feiertag"),
    pytest.param(WED, (time(18, 15), None), id="spaetere-huelle"),
    pytest.param(MON, (time(18, 15), time(23, 59)), id="gleiches-datum"),
]


def _assert_moved(db, e, target, ends, break_minutes):
    db.refresh(e)
    hours = Decimal("3.25") - Decimal(break_minutes) / 60
    assert (e.date, e.start_time, e.end_time, e.raw_end_time) == (target, time(15, 0), *ends)
    assert e.net_hours == hours.quantize(Decimal("0.01"))
    # Verschieben ist keine Korrektur des Endes: das Kennzeichen bleibt (P18).
    assert e.auto_closed is True


# ── MA-Antrag (E40): §4 prüft die angerechnete Zeit ─────────────────────────

@pytest.mark.parametrize("target", [
    pytest.param(SAT, id="samstag"),
    pytest.param(EASTER_MONDAY, id="feiertag"),
    pytest.param(MON, id="gleiches-datum"),
])
def test_change_request_checks_effective_end(_db_session, auto_closed_entry, employee_client, target):
    """3,25 h ohne Pause sind zulässig. Mit 15:00–23:59 (≈ 9 h) hätte §4 eine
    Pause von 30 Minuten verlangt und den Antrag abgelehnt."""
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(auto_closed_entry.id),
        "proposed_date": target.isoformat(), "proposed_start_time": "15:00",
        "proposed_end_time": "18:15", "proposed_break_minutes": 0,
        "reason": "Falscher Tag erfasst"})
    assert resp.status_code == 201, resp.text
    cr = _db_session.query(ChangeRequest).one()
    # Gespeichert wird weiter der rohe Vorschlag (E40).
    assert (cr.proposed_date, cr.proposed_end_time) == (target, time(18, 15))


# ── Antragsgenehmigung UPDATE (Vorprüfung + Schreiben) ──────────────────────

@pytest.mark.parametrize("target, ends", _MOVED)
def test_cr_approval_keeps_effective_end(_db_session, employee_user, auto_closed_entry, admin_client,
                                         target, ends):
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=auto_closed_entry.id, proposed_date=target,
                       proposed_start_time=time(15, 0), proposed_end_time=time(18, 15),
                       proposed_break_minutes=30, reason="Falscher Tag erfasst")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _assert_moved(_db_session, auto_closed_entry, target, ends, 30)


def test_cr_approval_precheck_uses_effective_end(_db_session, employee_user, auto_closed_entry, admin_client):
    """Vorprüfung (§4) mit demselben Ende wie das Schreiben: 3,25 h ohne Pause
    sind zulässig — mit 15:00–23:59 lehnte §4 die Genehmigung ab (422)."""
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=auto_closed_entry.id, proposed_date=SAT,
                       proposed_start_time=time(15, 0), proposed_end_time=time(18, 15),
                       proposed_break_minutes=0, reason="Falscher Tag erfasst")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _assert_moved(_db_session, auto_closed_entry, SAT, (time(18, 15), None), 0)


def test_cr_approval_real_end_on_other_day_is_a_correction(_db_session, employee_user, auto_closed_entry,
                                                           admin_client):
    """Gegenprobe: ein tatsächlich anderes Ende bleibt eine Korrektur — es gilt
    wie eingetragen und hebt das Kennzeichen auf (P18)."""
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=auto_closed_entry.id, proposed_date=SAT,
                       proposed_start_time=time(15, 0), proposed_end_time=time(19, 0),
                       proposed_break_minutes=0, reason="Ende nachgetragen")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(auto_closed_entry)
    assert (auto_closed_entry.end_time, auto_closed_entry.raw_end_time, auto_closed_entry.auto_closed) == (
        time(19, 0), None, False)


# ── Admin-Bearbeitung (/api/admin/time-entries) ─────────────────────────────

@pytest.mark.parametrize("target, ends", _MOVED)
@pytest.mark.parametrize("form", [True, False], ids=["formular", "nur-datum"])
def test_admin_route_date_move_keeps_effective_end(_db_session, auto_closed_entry, admin_client,
                                                   target, ends, form):
    """Formular (wirksames Ende 18:15 im Payload) und reiner Datums-PUT (Rückfall
    auf das gespeicherte Rohende) landen beide beim wirksamen Ende."""
    payload = {"date": target.isoformat()}
    if form:
        payload.update({"start_time": "15:00", "end_time": "18:15", "break_minutes": 30})
    resp = admin_client.put(f"/api/admin/time-entries/{auto_closed_entry.id}", json=payload)
    assert resp.status_code == 200, resp.text
    _assert_moved(_db_session, auto_closed_entry, target, ends, 30 if form else 0)


# ── Bearbeiten-Route der Beschäftigten (Admins, fremde Einträge) ────────────

@pytest.mark.parametrize("target, ends", _MOVED)
@pytest.mark.parametrize("form", [True, False], ids=["formular", "nur-datum"])
def test_employee_route_date_move_keeps_effective_end(_db_session, auto_closed_entry, admin_client,
                                                      target, ends, form):
    payload = {"date": target.isoformat()}
    if form:
        payload.update({"start_time": "15:00", "end_time": "18:15", "break_minutes": 30})
    resp = admin_client.put(f"/api/time-entries/{auto_closed_entry.id}", json=payload)
    assert resp.status_code == 200, resp.text
    _assert_moved(_db_session, auto_closed_entry, target, ends, 30 if form else 0)


# ── Helfer ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("incoming, eff, raw, auto_closed, prev, target, expected", [
    # Datumswechsel, Formular schickt wirksames Ende → wirksames Ende
    (time(18, 15), time(18, 15), time(23, 59), True, MON, SAT, time(18, 15)),
    # Datumswechsel, Rohende 23:59 zurück (Rückfall eines Teil-Updates) → wirksames Ende
    (time(23, 59), time(18, 15), time(23, 59), True, MON, SAT, time(18, 15)),
    # Datumswechsel mit echter Korrektur → Eingabe gilt
    (time(17, 0), time(18, 15), time(23, 59), True, MON, SAT, time(17, 0)),
    # gleiches Datum → unverändert P18 (Rohende als Kappungseingabe)
    (time(18, 15), time(18, 15), time(23, 59), True, MON, MON, time(23, 59)),
    # ohne Kennzeichen: Rohwert ist ein echter Stempel (unclamp_input)
    (time(18, 15), time(18, 15), time(19, 0), False, MON, SAT, time(19, 0)),
    # ohne Blöcke geschlossen: 23:59 ist das wirksame Ende
    (time(23, 59), time(23, 59), None, True, SAT, MON, time(23, 59)),
    # Ende entfernt
    (None, time(18, 15), time(23, 59), True, MON, SAT, None),
])
def test_end_input_for(incoming, eff, raw, auto_closed, prev, target, expected):
    from app.services.work_window_service import end_input_for
    assert end_input_for(incoming, eff, raw, auto_closed=auto_closed,
                         prev_date=prev, target_date=target) == expected
