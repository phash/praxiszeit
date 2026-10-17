"""Gesamtreview 1.20 (Review-Fund 8): die Genehmigung eines Zeiteintrags-
Antrags (CREATE/UPDATE) prüft das Beschäftigungsfenster neu.

Geprüft wurde nur beim Stellen des Antrags. Setzt die Verwaltung danach den
ersten bzw. letzten Arbeitstag, entstand bei der Genehmigung ein Eintrag
außerhalb des Fensters — er fiele still aus dem gefensterten Ist (#195) und
damit aus Saldo und Summenzeilen der Exporte. Der Abwesenheitszweig desselben
Endpunkts und die Verwaltungswege (``admin_create/update_time_entry``, #502)
lehnen das mit 400 ab. Wie dort zählt bei UPDATE nur ein tatsächlicher
Datumswechsel: ein Alteintrag außerhalb eines später gesetzten Fensters bleibt
per Zeitkorrektur reparierbar.
"""
from datetime import date, time

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)

SEP_26 = date(2026, 9, 25)   # Freitag
SEP_29 = date(2026, 9, 29)   # Dienstag
AFTER = "Datum liegt nach dem letzten Arbeitstag"
BEFORE = "Datum liegt vor dem ersten Arbeitstag"


def _entry(db, user, d, start, end):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=0)
    db.add(e)
    db.commit()
    return e


def _cr(db, user, d, start, end, *, entry=None, rtype=ChangeRequestType.CREATE):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
        request_type=rtype, status=ChangeRequestStatus.PENDING,
        time_entry_id=entry.id if entry else None, proposed_date=d,
        proposed_start_time=start, proposed_end_time=end, proposed_break_minutes=0,
        original_date=entry.date if entry else None,
        original_start_time=entry.start_time if entry else None,
        original_end_time=entry.end_time if entry else None,
        original_break_minutes=0 if entry else None,
        reason="nachgetragen")
    db.add(cr)
    db.commit()
    return cr


def _approve(client, cr):
    return client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})


def _status(db, cr):
    db.expire_all()
    return db.get(ChangeRequest, cr.id).status


def test_create_after_last_work_day_set_later_is_400(_db_session, employee_user, admin_client):
    """Antrag für den 29.09., danach letzter Arbeitstag 25.09. eingetragen."""
    cr = _cr(_db_session, employee_user, SEP_29, time(8, 0), time(12, 0))
    employee_user.last_work_day = SEP_26
    _db_session.commit()

    r = _approve(admin_client, cr)

    assert r.status_code == 400, r.text
    assert r.json()["detail"] == AFTER
    assert _status(_db_session, cr) == ChangeRequestStatus.PENDING
    assert _db_session.query(TimeEntry).count() == 0


def test_create_before_first_work_day_set_later_is_400(_db_session, employee_user, admin_client):
    cr = _cr(_db_session, employee_user, SEP_26, time(8, 0), time(12, 0))
    employee_user.first_work_day = SEP_29
    _db_session.commit()

    r = _approve(admin_client, cr)

    assert r.status_code == 400, r.text
    assert r.json()["detail"] == BEFORE
    assert _status(_db_session, cr) == ChangeRequestStatus.PENDING
    assert _db_session.query(TimeEntry).count() == 0


def test_update_moving_out_of_window_is_400(_db_session, employee_user, admin_client):
    e = _entry(_db_session, employee_user, SEP_26, time(8, 0), time(12, 0))
    cr = _cr(_db_session, employee_user, SEP_29, time(8, 0), time(12, 0),
             entry=e, rtype=ChangeRequestType.UPDATE)
    employee_user.last_work_day = SEP_26
    _db_session.commit()

    r = _approve(admin_client, cr)

    assert r.status_code == 400, r.text
    assert r.json()["detail"] == AFTER
    assert _status(_db_session, cr) == ChangeRequestStatus.PENDING
    assert _db_session.get(TimeEntry, e.id).date == SEP_26


def test_update_same_date_outside_later_window_stays_correctable(
    _db_session, employee_user, admin_client,
):
    """Kontrolle: kein Datumswechsel — der Alteintrag lässt sich korrigieren."""
    e = _entry(_db_session, employee_user, SEP_29, time(8, 0), time(12, 0))
    cr = _cr(_db_session, employee_user, SEP_29, time(8, 0), time(11, 30),
             entry=e, rtype=ChangeRequestType.UPDATE)
    employee_user.last_work_day = SEP_26
    _db_session.commit()

    r = _approve(admin_client, cr)

    assert r.status_code == 200, r.text
    assert _status(_db_session, cr) == ChangeRequestStatus.APPROVED
    assert _db_session.get(TimeEntry, e.id).end_time == time(11, 30)


def test_create_inside_window_is_approved(_db_session, employee_user, admin_client):
    """Kontrolle: im Fenster unverändert genehmigt."""
    cr = _cr(_db_session, employee_user, SEP_26, time(8, 0), time(12, 0))
    employee_user.last_work_day = SEP_26
    _db_session.commit()

    r = _approve(admin_client, cr)

    assert r.status_code == 200, r.text
    assert _status(_db_session, cr) == ChangeRequestStatus.APPROVED


def test_bulk_reports_window_failure_per_item(_db_session, employee_user, admin_client):
    bad = _cr(_db_session, employee_user, SEP_29, time(8, 0), time(12, 0))
    good = _cr(_db_session, employee_user, SEP_26, time(8, 0), time(12, 0))
    employee_user.last_work_day = SEP_26
    _db_session.commit()

    r = admin_client.post("/api/admin/change-requests/bulk-review", json={
        "request_ids": [str(bad.id), str(good.id)], "action": "approve",
    })

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["succeeded"], body["failed"]) == (1, 1)
    by_id = {i["request_id"]: i for i in body["items"]}
    assert by_id[str(bad.id)]["status"] == "failed"
    assert by_id[str(bad.id)]["error"] == AFTER
    assert by_id[str(good.id)]["status"] == "approved"
