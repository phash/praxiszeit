"""Gesamtreview 1.20 (Fund 1): die F1-Klemmung (Spec 9.6, „Misch-Tage") gilt
auch an den Einzel-Schreibpfaden, die eine Seite des Misch-Tags ändern.

F1: bleiben an einem Abwesenheitstag geschlossene Zeiteinträge stehen, trägt die
Abwesenheit nur den NICHT gearbeiteten Rest (``calculation_service.f1_clamp_hours``)
— sonst zählt das Ist die Arbeit UND die volle Gutschrift (Phantom-Saldo). Das
setzten bis hierher nur die Direktbuchung (``absences.create_absence``) und die
Rückrechnung (``retarget_absence_hours``) durch:

* **Anerkennen** (Admin-Aktion und „Genehmigen und anerkennen") hob das Netto
  des Eintrags auf die volle gestempelte Zeit und ließ die beim Buchen geklemmte
  Krank-Gutschrift stehen. Erst buchen, dann anerkennen ergab +1,25 h; erst
  anerkennen, dann buchen das Richtige (reihenfolgeabhängig). Die nächste
  Arbeitszeit-Änderung über den Tag klemmte zurück und meldete das als
  Verkürzung 9.5 (c) — im abgeschlossenen Jahr gesperrt.
* **Abwesenheits-Antrag UPDATE** (gleicher Tag, gleicher Typ — die Einträge des
  Tages bleiben stehen) setzte ``hours`` bedingungslos auf das volle Tagessoll.
"""
from datetime import time
from decimal import Decimal

import pytest

from app.models import Absence, AbsenceType, ChangeRequest, TimeEntry, TimeEntryAuditLog
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.services import calculation_service as cs
from app.services import credit_override_service as cos
from app.services.export_service import format_hours_de
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON, block_week

TUE = MON.replace(day=2)

# Blöcke Mo 08:00–16:30, Pause 30 → Tagessoll 8 h (40 h/Woche), Hülle 07:45–16:45.
_WEEK = block_week(pause=30, mon=[("08:00", "16:30")])


def _clamped_morning(db, user):
    """06:30 eingestempelt (gekappt auf 07:45), 10:30 krank nach Hause: 2,75 h
    angerechnet, 1:15 h vor der Hülle nicht angerechnet."""
    user.work_blocks = _WEEK
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                  start_time=time(7, 45), end_time=time(10, 30), raw_start_time=time(6, 30),
                  break_minutes=0, uncredited_minutes=0, clamp_grace_minutes=15)
    db.add(e)
    db.commit()
    assert float(e.net_hours) == 2.75
    return e


def _book_sick_keeping_entries(client, user, day=MON):
    # Der „+"-Knopf im Monatsjournal schickt keep_time_entries automatisch.
    r = client.post("/api/absences/", json={
        "user_id": str(user.id), "date": day.isoformat(), "type": "sick", "hours": 8.0,
        "keep_time_entries": True,
    })
    assert r.status_code == 201, r.text
    [booked] = r.json()
    return booked["id"]


def _absence(db, user, day=MON):
    db.expire_all()
    return db.query(Absence).filter(Absence.user_id == user.id, Absence.date == day).one()


def _day_saldo(db, user, day=MON):
    return cs.get_range_actual(db, user, day, day) - cs.get_range_target(db, user, day, day)


def _no_reduction_left(db, user, day=MON):
    """Die nächste Rückrechnung über den Tag (unveränderter Vertrag) findet
    nichts mehr — keine Verkürzung 9.5 (c) aus einer eben entstandenen
    Doppelanrechnung."""
    return cs.retarget_absence_hours(
        db, user, day, day,
        old_full_target_by_date=cs.absence_full_targets(db, user, day, day),
        dry_run=True,
    ) == []


def _absence_logs(db):
    return db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.source == cos.CREDIT_OVERRIDE_SOURCE,
        TimeEntryAuditLog.time_entry_id.is_(None),
    ).all()


def test_recognizing_after_sick_booking_reclamps_the_credit(
    _db_session, employee_user, admin_user, admin_client,
):
    e = _clamped_morning(_db_session, employee_user)
    _book_sick_keeping_entries(admin_client, employee_user)
    assert float(_absence(_db_session, employee_user).hours) == 5.25    # 8 − 2,75
    assert _day_saldo(_db_session, employee_user) == 0

    r = admin_client.post(f"/api/admin/time-entries/{e.id}/credit-override")
    assert r.status_code == 200, r.text
    assert r.json()["net_hours"] == 4.0

    a = _absence(_db_session, employee_user)
    assert float(a.hours) == 4.0                 # 8 − 4,0 (vorher blieb 5,25 stehen)
    assert float(a.raw_hours) == 5.25            # gebuchter Wert bleibt die Rückversicherung
    assert _day_saldo(_db_session, employee_user) == 0     # vorher +1,25 h Phantom
    assert _no_reduction_left(_db_session, employee_user)

    [log] = _absence_logs(_db_session)
    assert (log.user_id, log.changed_by, log.action) == (employee_user.id, admin_user.id, "update")
    assert (log.old_date, log.new_date, log.change_request_id) == (MON, MON, None)
    assert log.old_note == f"Krank {format_hours_de(Decimal('5.25'))} h"
    assert log.new_note == (
        f"Krank {format_hours_de(Decimal('4.00'))} h — {cos.MIXED_DAY_TRIGGER}")
    assert log.row_hash   # #121: über die Objektschicht geschrieben


def test_order_of_booking_and_recognizing_does_not_matter(
    _db_session, employee_user, admin_client,
):
    """Erst anerkennen, dann buchen: dasselbe Ergebnis wie oben."""
    e = _clamped_morning(_db_session, employee_user)
    assert admin_client.post(f"/api/admin/time-entries/{e.id}/credit-override").status_code == 200
    _book_sick_keeping_entries(admin_client, employee_user)
    assert float(_absence(_db_session, employee_user).hours) == 4.0
    assert _day_saldo(_db_session, employee_user) == 0
    # Beim Anerkennen stand noch keine Abwesenheit — nichts angeglichen.
    assert _absence_logs(_db_session) == []


def test_recognizing_without_absence_writes_no_absence_row(
    _db_session, employee_user, admin_client,
):
    e = _clamped_morning(_db_session, employee_user)
    assert admin_client.post(f"/api/admin/time-entries/{e.id}/credit-override").status_code == 200
    assert _absence_logs(_db_session) == []


def test_grant_and_recognize_on_approval_reclamps_the_credit(
    _db_session, employee_user, admin_client,
):
    """„Genehmigen und anerkennen" läuft durch dieselbe Quelle."""
    e = _clamped_morning(_db_session, employee_user)
    _book_sick_keeping_entries(admin_client, employee_user)
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="time_entry",
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
        time_entry_id=e.id, proposed_date=MON, proposed_start_time=time(6, 30),
        proposed_end_time=time(10, 30), proposed_break_minutes=0,
        reason="Ab 06:30 Patienten versorgt",
    )
    _db_session.add(cr)
    _db_session.commit()
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review",
                          json={"action": "approve", "grant_credit_override": True})
    assert r.status_code == 200, r.text
    assert float(_absence(_db_session, employee_user).hours) == 4.0
    assert _day_saldo(_db_session, employee_user) == 0
    assert _no_reduction_left(_db_session, employee_user)
    [log] = _absence_logs(_db_session)
    assert log.change_request_id == cr.id


def _sick_with_kept_entry(db, user, client, day=MON):
    """08:00–11:00 gearbeitet (ohne Blöcke), dann krank: Gutschrift 5 h."""
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=day,
                     start_time=time(8), end_time=time(11), break_minutes=0))
    db.commit()
    absence_id = _book_sick_keeping_entries(client, user, day)
    assert float(_absence(db, user, day).hours) == 5.0
    return absence_id


def _absence_update_cr(db, user, absence_id, day):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="absence",
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
        absence_id=absence_id, proposed_date=day, proposed_absence_type="sick",
        reason="Notiz ergänzt",
    )
    db.add(cr)
    db.commit()
    return cr


def test_absence_update_request_on_the_same_day_keeps_the_clamp(
    _db_session, employee_user, admin_client,
):
    absence_id = _sick_with_kept_entry(_db_session, employee_user, admin_client)
    cr = _absence_update_cr(_db_session, employee_user, absence_id, MON)
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    a = _absence(_db_session, employee_user)
    assert float(a.hours) == 5.0                 # vorher: volles Tagessoll 8 h
    assert float(a.raw_hours) == 5.0             # Neubuchung durch einen Menschen
    assert _db_session.query(TimeEntry).filter(TimeEntry.date == MON).count() == 1
    assert _day_saldo(_db_session, employee_user) == 0     # vorher +3 h Phantom
    assert _no_reduction_left(_db_session, employee_user)


def test_absence_update_request_moving_the_day_clears_entries_and_books_the_full_target(
    _db_session, employee_user, admin_client,
):
    """Unverändert: zieht die Abwesenheit auf einen anderen Tag, ersetzt sie
    dessen Einträge (Fix #3) — dort bleibt nichts zu klemmen."""
    absence_id = _sick_with_kept_entry(_db_session, employee_user, admin_client)
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=TUE,
                              start_time=time(8), end_time=time(10), break_minutes=0))
    _db_session.commit()
    cr = _absence_update_cr(_db_session, employee_user, absence_id, TUE)
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert float(_absence(_db_session, employee_user, TUE).hours) == 8.0
    assert _db_session.query(TimeEntry).filter(TimeEntry.date == TUE).count() == 0


@pytest.mark.parametrize("half_day, expected", [(False, 5.0), (True, 4.0)])
def test_absence_update_request_clamps_from_the_booked_share(
    _db_session, employee_user, admin_client, half_day, expected,
):
    """Halbtag: ½ × 8 = 4 h ≤ Rest 5 h — bleibt (wie beim Buchen)."""
    absence_id = _sick_with_kept_entry(_db_session, employee_user, admin_client)
    a = _absence(_db_session, employee_user)
    a.half_day = half_day
    _db_session.commit()
    cr = _absence_update_cr(_db_session, employee_user, absence_id, MON)
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert float(_absence(_db_session, employee_user).hours) == expected
