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

Zwei Schritte (PR1-Review N2): Montag → Freitag (frühere Hülle bis 16:15) →
nächster Montag muss dasselbe ergeben wie der direkte Weg (18:15, 3,25 h).
Nach dem ersten Schritt trägt das Rohende das übernommene wirksame Ende 18:15 —
es ist die Kappungseingabe des zweiten Schritts, nicht das schon gekürzte 16:15.
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
FRI = date(2026, 6, 5)    # Freitag — letzter Block bis 16:00, Hülle bis 16:15
MON2 = date(2026, 6, 8)   # nächster Montag — Hülle wie MON bis 18:15
# Montag wie K_BLOCKS (Hülle 07:45–18:15), Mittwoch mit späterer Hülle,
# Freitag mit früherer Hülle.
WEEK = block_week(
    mon=[("08:00", "12:00"), ("15:00", "18:00")],
    wed=[("08:00", "20:00")],
    fri=[("08:00", "12:00"), ("15:00", "16:00")],
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
    pytest.param(MON2, (time(18, 15), None), id="naechster-montag"),
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


# ── Zwei Schritte: Ergebnis unabhängig von der Reihenfolge (PR1-Review N2) ──

def _assert_on_friday(db, e):
    """Montag → Freitag: 18:15 wird auf die Hülle 16:15 gekappt, das Rohende trägt
    das übernommene wirksame Ende 18:15 (kein Stempel, Kennzeichen bleibt)."""
    db.refresh(e)
    assert (e.date, e.end_time, e.raw_end_time, e.net_hours, e.auto_closed) == (
        FRI, time(16, 15), time(18, 15), Decimal("1.25"), True)


@pytest.mark.parametrize("route", ["/api/admin/time-entries", "/api/time-entries"],
                         ids=["admin-route", "ma-route"])
@pytest.mark.parametrize("second_end", ["16:15", "18:15", None],
                         ids=["formular", "rohende-eingetippt", "nur-datum"])
def test_route_two_moves_do_not_depend_on_order(_db_session, auto_closed_entry, admin_client,
                                                route, second_end):
    """Montag → Freitag → nächster Montag = 18:15 / 3,25 h wie der direkte Weg.
    Bis zum Fix kappte der zweite Schritt mit dem schon gekürzten 16:15 —
    2 h fielen still weg (keine Kappungswarnung, am Montag ist 16:15 konform).
    Auch ein ausdrücklich eingetipptes 18:15 landete bei 16:15."""
    url = f"{route}/{auto_closed_entry.id}"
    first = {"date": FRI.isoformat()}
    if second_end is not None:
        first.update({"start_time": "15:00", "end_time": "18:15", "break_minutes": 0})
    resp = admin_client.put(url, json=first)
    assert resp.status_code == 200, resp.text
    _assert_on_friday(_db_session, auto_closed_entry)

    second = {"date": MON2.isoformat()}
    if second_end is not None:
        second.update({"start_time": "15:00", "end_time": second_end, "break_minutes": 0})
    resp = admin_client.put(url, json=second)
    assert resp.status_code == 200, resp.text
    _assert_moved(_db_session, auto_closed_entry, MON2, (time(18, 15), None), 0)


@pytest.mark.parametrize("second_end", [time(16, 15), time(18, 15)],
                         ids=["formular", "rohende-eingetippt"])
def test_cr_approval_two_moves_do_not_depend_on_order(_db_session, employee_user, auto_closed_entry,
                                                      admin_client, second_end):
    for target, end in ((FRI, time(18, 15)), (MON2, second_end)):
        cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
                           entry_kind="time_entry", request_type=ChangeRequestType.UPDATE,
                           status=ChangeRequestStatus.PENDING, time_entry_id=auto_closed_entry.id,
                           proposed_date=target, proposed_start_time=time(15, 0),
                           proposed_end_time=end, proposed_break_minutes=0,
                           reason="Falscher Tag erfasst")
        _db_session.add(cr)
        _db_session.commit()
        resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review",
                                 json={"action": "approve"})
        assert resp.status_code == 200, resp.text
        if target == FRI:
            _assert_on_friday(_db_session, auto_closed_entry)
    _assert_moved(_db_session, auto_closed_entry, MON2, (time(18, 15), None), 0)


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
    # zweiter Datumswechsel: das Rohende trägt das übernommene wirksame Ende
    # (kein 23:59) → es ist die Eingabe, nicht das schon gekürzte wirksame Ende
    (time(16, 15), time(16, 15), time(18, 15), True, FRI, MON2, time(18, 15)),
    (time(18, 15), time(16, 15), time(18, 15), True, FRI, MON2, time(18, 15)),
    # dasselbe am gleichen Tag → unclamp_input (unverändert)
    (time(16, 15), time(16, 15), time(18, 15), True, FRI, FRI, time(18, 15)),
    # Ende entfernt
    (None, time(18, 15), time(23, 59), True, MON, SAT, None),
    # Review Task 6 (PR2): minutengenau — 23:59:30 ist das synthetische 23:59,
    # am selben Tag bleibt das gespeicherte Rohende (keine Sekunden), beim
    # Verschieben gilt das wirksame Ende
    (time(23, 59, 30), time(18, 15), time(23, 59), True, MON, MON, time(23, 59)),
    (time(23, 59, 30), time(18, 15), time(23, 59), True, MON, SAT, time(18, 15)),
    (time(18, 15, 30), time(18, 15), time(23, 59), True, MON, MON, time(23, 59)),
    # ein gespeichertes Rohende 23:59:xx gilt ebenfalls als synthetisch
    (time(18, 15), time(18, 15), time(23, 59, 30), True, MON, SAT, time(18, 15)),
])
def test_end_input_for(incoming, eff, raw, auto_closed, prev, target, expected):
    from app.services.work_window_service import end_input_for
    assert end_input_for(incoming, eff, raw, auto_closed=auto_closed,
                         prev_date=prev, target_date=target) == expected


# ── Reihenfolge der tatsächlichen Kappungseingaben (PR1-Review N2-Nachzug) ──
#
# ``end_input_for`` ersetzt beim Verschieben das synthetische 23:59 durch das
# wirksame Ende 18:15 — die Prüfung „Endzeit muss nach Startzeit liegen" lief
# aber vorher auf der rohen Eingabe (23:59 bzw. dem Rückfall darauf). Mit einem
# späteren Beginn landete der Eintrag als 20:00–18:15, net 0, ohne Warnung —
# genau der Zustand, den der Release-Review 1.16.0 ausschließen wollte (der Tag
# verschwindet still aus Saldo und §16-Beleg). Jetzt 400, Eintrag unverändert.

def _assert_unchanged(db, e):
    # Produktiv schließt ``get_db`` die Sitzung (= Rollback); im Test teilen sich
    # Route und Test die Sitzung — die MA-Route setzt Felder vor dem 400.
    db.rollback()
    db.refresh(e)
    assert (e.date, e.start_time, e.end_time, e.raw_end_time, e.net_hours, e.auto_closed) == (
        MON, time(15, 0), time(18, 15), time(23, 59), Decimal("3.25"), True)


def _assert_order_rejected(resp):
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail.startswith("Endzeit muss nach Startzeit liegen")
    # Hinweis: das Ende ist kein Stempel, ein tatsächliches Ende ist einzutragen.
    assert "automatisch geschlossen" in detail


@pytest.mark.parametrize("route", ["/api/admin/time-entries", "/api/time-entries"],
                         ids=["admin-route", "ma-route"])
@pytest.mark.parametrize("target, start", [
    pytest.param(SAT, "20:00", id="samstag"),
    pytest.param(MON2, "19:00", id="naechster-montag"),
])
@pytest.mark.parametrize("end", ["23:59", None], ids=["ende-2359-eingetippt", "ohne-ende"])
def test_route_start_after_effective_end_rejected(_db_session, auto_closed_entry, admin_client,
                                                  route, target, start, end):
    payload = {"date": target.isoformat(), "start_time": start}
    if end is not None:
        payload.update({"end_time": end, "break_minutes": 0})
    resp = admin_client.put(f"{route}/{auto_closed_entry.id}", json=payload)
    if route == "/api/time-entries" and end is None:
        # Die MA-Route füllt das Ende mit dem gespeicherten wirksamen Ende auf —
        # die bestehende Prüfung greift schon (ohne Hinweis).
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Endzeit muss nach Startzeit liegen")
    else:
        _assert_order_rejected(resp)
    _assert_unchanged(_db_session, auto_closed_entry)


@pytest.mark.parametrize("target, start", [
    pytest.param(SAT, "20:00", id="samstag"),
    pytest.param(MON2, "19:00", id="naechster-montag"),
])
def test_change_request_start_after_effective_end_rejected(_db_session, auto_closed_entry,
                                                           employee_client, target, start):
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(auto_closed_entry.id),
        "proposed_date": target.isoformat(), "proposed_start_time": start,
        "proposed_end_time": "23:59", "proposed_break_minutes": 0,
        "reason": "Falscher Tag erfasst"})
    _assert_order_rejected(resp)
    assert _db_session.query(ChangeRequest).count() == 0
    _assert_unchanged(_db_session, auto_closed_entry)


@pytest.mark.parametrize("target, start", [
    pytest.param(SAT, time(20, 0), id="samstag"),
    pytest.param(MON2, time(19, 0), id="naechster-montag"),
])
def test_cr_approval_start_after_effective_end_rejected(_db_session, employee_user, auto_closed_entry,
                                                        admin_client, target, start):
    """Auch ein älterer Antrag (vor dieser Prüfung gestellt) wird nicht genehmigt —
    vor der Vorprüfung und vor jeder Statusänderung."""
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=auto_closed_entry.id, proposed_date=target,
                       proposed_start_time=start, proposed_end_time=time(23, 59),
                       proposed_break_minutes=0, reason="Falscher Tag erfasst")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    _assert_order_rejected(resp)
    _assert_unchanged(_db_session, auto_closed_entry)
    _db_session.refresh(cr)
    assert cr.status == ChangeRequestStatus.PENDING


@pytest.mark.parametrize("start, end, auto_closed, expected", [
    (time(20, 0), time(18, 15), True, "auto"),
    (time(18, 15), time(18, 15), True, "auto"),
    (time(20, 0), time(18, 15), False, "plain"),
    (time(15, 0), time(18, 15), True, None),
    (time(15, 0), None, True, None),
    (None, time(18, 15), False, None),
])
def test_input_order_error(start, end, auto_closed, expected):
    from app.services.work_window_service import input_order_error
    detail = input_order_error(start, end, auto_closed=auto_closed)
    if expected is None:
        assert detail is None
    else:
        assert detail.startswith("Endzeit muss nach Startzeit liegen")
        assert ("automatisch geschlossen" in detail) is (expected == "auto")
