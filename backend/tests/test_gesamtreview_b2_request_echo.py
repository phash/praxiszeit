"""Gesamtreview 1.20 (B2, Punkt 1): veraltetes Echo bei der Antragsgenehmigung
OHNE ``auto_closed``.

Ein Antrag, der nur Pause oder Notiz ändert, schickt die angerechneten Zeiten
unverändert zurück (das Antragsformular belegt sie vor). Beide Antragswege
halten den angerechneten Stand ZUM ZEITPUNKT DES ANTRAGS als
``original_start_time``/``original_end_time`` fest. Ändert eine Neukappung
(Spec 9.2) die angerechnete Zeit vor der Genehmigung, war das Echo nicht mehr
gleich dem aktuellen Wert: ``unclamp_input`` hielt es für eine neue Eingabe,
``clamp`` legte es als Rohwert ab — der echte Stempel (§16, Grundlage der
§5-Ruhezeit) war weg. Für ``auto_closed`` galt die Regel schon (Review V1,
``request_end_for_approval``); sie gilt jetzt für jeden Eintrag und auch für
den Beginn.
"""
from datetime import time

import pytest

from app.models import ChangeRequest, TimeEntry
from app.services import work_window_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

# Mo 08–12 + 15–17 → Hülle bis 17:15 (Beginn weiter 07:45).
SHORTER_END = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")])
# Mo 09–12 + 15–18 → Hülle ab 08:45 (Ende weiter 18:15).
LATER_START = block_week(mon=[("09:00", "12:00"), ("15:00", "18:00")])


def _as_admin(admin_user):
    """Nach einem Schritt als Beschäftigte die Verwaltung handeln lassen —
    dieselben Überschreibungen wie ``admin_client``, im selben Client."""
    from tests.test_endpoints import endpoints_app, get_current_user, require_admin
    endpoints_app.dependency_overrides[get_current_user] = lambda: admin_user
    endpoints_app.dependency_overrides[require_admin] = lambda: admin_user


def _reclamp_monday(db, user, blocks):
    """Die Verwaltung ändert rückwirkend die Blöcke des Montags → Massen-
    Neukappung (Spec 9.2) mit dem Mandanten-Puffer 15, Quelle Rohstempel."""
    user.work_blocks = blocks
    db.flush()
    work_window_service.reclamp_time_entries(db, user, MON, MON, {0}, None, 15)
    db.commit()


def _stamped(db, user, start, end):
    """Gestempelter, geschlossener Eintrag, gegen K_BLOCKS gekappt wie nach dem
    Ausstempeln (über dieselbe Neukappung, Quelle = die gespeicherte Zeit)."""
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                  start_time=start, end_time=end, break_minutes=0)
    db.add(e)
    db.commit()
    _reclamp_monday(db, user, K_BLOCKS)
    db.refresh(e)
    return e


def _echo_request(client, db, entry):
    """Gewöhnlicher MA-Antrag „Notiz nachgetragen" mit den vorbelegten
    (angerechneten) Zeiten — der echte Antragsweg."""
    resp = client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(entry.id),
        "proposed_date": MON.isoformat(),
        "proposed_start_time": entry.start_time.strftime("%H:%M"),
        "proposed_end_time": entry.end_time.strftime("%H:%M"),
        "proposed_break_minutes": 0, "proposed_note": "Fortbildung vormittags",
        "reason": "Notiz nachgetragen"})
    assert resp.status_code == 201, resp.text
    return db.query(ChangeRequest).one()


def test_echoed_end_after_reclamp_keeps_raw_stamp(_db_session, employee_user, admin_user,
                                                  employee_client):
    """Der Fall aus dem Review: Rohstempel 19:00, angerechnet 18:15, der Antrag
    schickt 18:15 zurück; danach kürzt die Neukappung auf 17:15. Die
    Genehmigung behält den Rohstempel 19:00 und rechnet bis 17:15 an."""
    e = _stamped(_db_session, employee_user, time(8, 0), time(19, 0))
    assert (e.end_time, e.raw_end_time) == (time(18, 15), time(19, 0))
    cr = _echo_request(employee_client, _db_session, e)
    assert cr.original_end_time == time(18, 15)

    _reclamp_monday(_db_session, employee_user, SHORTER_END)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time) == (time(17, 15), time(19, 0))

    _as_admin(admin_user)
    resp = employee_client.post(f"/api/admin/change-requests/{cr.id}/review",
                                json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.start_time, e.raw_start_time) == (time(8, 0), None)
    assert (e.end_time, e.raw_end_time) == (time(17, 15), time(19, 0))
    assert e.note == "Fortbildung vormittags"
    # Lücke 12:15–14:45 + Hülle 17:15–19:00.
    assert work_window_service.not_credited_minutes(e) == 150 + 105


def test_echoed_start_after_reclamp_keeps_raw_stamp(_db_session, employee_user, admin_user,
                                                    employee_client):
    """Dasselbe am Beginn: Rohstempel 07:00, angerechnet 07:45, der Antrag
    schickt 07:45 zurück; danach beginnt die Hülle erst 08:45. Die Genehmigung
    behält den Rohstempel 07:00 (sonst stünde 07:45 als Stempel da)."""
    e = _stamped(_db_session, employee_user, time(7, 0), time(18, 0))
    assert (e.start_time, e.raw_start_time) == (time(7, 45), time(7, 0))
    cr = _echo_request(employee_client, _db_session, e)
    assert cr.original_start_time == time(7, 45)

    _reclamp_monday(_db_session, employee_user, LATER_START)
    _db_session.refresh(e)
    assert (e.start_time, e.raw_start_time) == (time(8, 45), time(7, 0))

    _as_admin(admin_user)
    resp = employee_client.post(f"/api/admin/change-requests/{cr.id}/review",
                                json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.start_time, e.raw_start_time) == (time(8, 45), time(7, 0))
    assert (e.end_time, e.raw_end_time) == (time(18, 0), None)


def test_typed_end_after_reclamp_stays_an_input(_db_session, employee_user, admin_user,
                                                employee_client):
    """Gegenprobe: ein im Antrag eingetipptes anderes Ende (18:45) ist eine
    Eingabe und wird nach der Neukappung gegen die neue Hülle gekappt."""
    e = _stamped(_db_session, employee_user, time(8, 0), time(19, 0))
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id),
        "proposed_date": MON.isoformat(), "proposed_start_time": "08:00",
        "proposed_end_time": "18:45", "proposed_break_minutes": 0,
        "reason": "Ende korrigiert"})
    assert resp.status_code == 201, resp.text
    cr = _db_session.query(ChangeRequest).one()
    _reclamp_monday(_db_session, employee_user, SHORTER_END)

    _as_admin(admin_user)
    resp = employee_client.post(f"/api/admin/change-requests/{cr.id}/review",
                                json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time) == (time(17, 15), time(18, 45))


# Unit: Echo = angerechneter Wert zum Zeitpunkt des Antrags → aktueller Wert;
# jeder andere Wert bleibt, wie er beantragt wurde.
@pytest.mark.parametrize("auto_closed", [False, True])
@pytest.mark.parametrize("proposed, original, expected", [
    (time(18, 15), time(18, 15), time(17, 15)),       # Echo, seither neu gekappt
    (time(18, 15, 30), time(18, 15), time(17, 15)),   # minutengenau
    (time(18, 45), time(18, 15), time(18, 45)),       # eingetippt: bleibt Eingabe
    (time(18, 15), None, time(18, 15)),               # Antrag zu einem damals offenen Eintrag
    (None, time(18, 15), None),                       # kein Ende beantragt
])
def test_request_end_for_approval_any_entry(auto_closed, proposed, original, expected):
    entry = TimeEntry(end_time=time(17, 15), raw_end_time=time(19, 0), auto_closed=auto_closed)
    assert work_window_service.request_end_for_approval(entry, proposed, original) == expected


@pytest.mark.parametrize("proposed, original, expected", [
    (time(7, 45), time(7, 45), time(8, 45)),          # Echo, seither neu gekappt
    (time(7, 45, 20), time(7, 45), time(8, 45)),      # minutengenau
    (time(7, 30), time(7, 45), time(7, 30)),          # eingetippt: bleibt Eingabe
    (time(7, 45), None, time(7, 45)),                 # kein Vorher-Wert
    (None, time(7, 45), None),
])
def test_request_start_for_approval(proposed, original, expected):
    entry = TimeEntry(start_time=time(8, 45), raw_start_time=time(7, 0))
    assert work_window_service.request_start_for_approval(entry, proposed, original) == expected
