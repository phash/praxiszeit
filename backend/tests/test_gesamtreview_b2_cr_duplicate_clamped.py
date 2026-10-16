"""Gesamtreview 1.20 (B2, Review-Fund): die Duplikatprüfung der
Antragsgenehmigung prüft den GEKAPPTEN Beginn.

Gespeichert wird bei der Genehmigung ``clamp(...).eff_start``; geprüft wurde
der beantragte (CREATE) bzw. der für die Genehmigung gelesene Beginn (UPDATE,
``request_start_for_approval``) — beide VOR dem Kappen. Fiel der gekappte
Beginn auf den Beginn eines anderen Eintrags desselben Tages, rutschte die
Genehmigung an der Sonde vorbei und scheiterte an ``uq_tenant_user_date_start``
(IntegrityError → HTTP 500). Der Antrag blieb offen und liess sich nur noch
ablehnen; in der Sammel-Genehmigung brach der ganze Aufruf mit 500 ab, weil
``except HTTPException`` den IntegrityError nicht fängt. Die beiden direkten
Schreibwege (``time_entries.create_time_entry``, ``admin_time_entries``) prüfen
seit Release-Review 1.16.0 nach dem Kappen — die Genehmigung ist ein paralleler
Schreibpfad und zieht jetzt nach.
"""
from datetime import date, time

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

TUE = date(2026, 6, 2)
# Mo wie K_BLOCKS (Hülle 07:45–18:15), Di 07:00–12:00 (Hülle 06:45–12:15).
MON_TUE = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("07:00", "12:00")])

DUP_DETAIL = "Ein Zeiteintrag mit diesem Datum und dieser Startzeit existiert bereits."


def _entry(db, user, d, start, end, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=0, **kw)
    db.add(e)
    db.commit()
    return e


def _cr(db, user, entry, d, start, end, *, rtype=ChangeRequestType.UPDATE):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
        request_type=rtype, status=ChangeRequestStatus.PENDING,
        time_entry_id=entry.id if entry else None, proposed_date=d,
        proposed_start_time=start, proposed_end_time=end, proposed_break_minutes=0,
        original_date=entry.date if entry else None,
        original_start_time=entry.start_time if entry else None,
        original_end_time=entry.end_time if entry else None,
        original_break_minutes=0 if entry else None,
        reason="Zeit korrigiert")
    db.add(cr)
    db.commit()
    return cr


def _approve(client, cr):
    return client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})


def _assert_untouched(db, cr, entry=None, start=None, raw_start=None):
    """409 vor jeder Statusänderung: Antrag offen, Eintrag unverändert."""
    db.expire_all()
    assert db.get(ChangeRequest, cr.id).status == ChangeRequestStatus.PENDING
    if entry is not None:
        stored = db.get(TimeEntry, entry.id)
        assert stored.start_time == start
        assert stored.raw_start_time == raw_start


def test_update_typed_start_clamped_onto_sibling_is_409(_db_session, employee_user, admin_client):
    """(a) Beantragter Beginn 07:30 liegt vor der Hülle und wird auf 07:45
    gekappt — dort beginnt schon ein anderer Eintrag."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    _entry(_db_session, employee_user, MON, time(7, 45), time(8, 30))
    b = _entry(_db_session, employee_user, MON, time(9, 30), time(12, 0))
    cr = _cr(_db_session, employee_user, b, MON, time(7, 30), time(12, 0))

    r = _approve(admin_client, cr)

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == DUP_DETAIL
    _assert_untouched(_db_session, cr, b, time(9, 30), None)


def test_update_echo_moved_to_day_with_earlier_hull_is_409(_db_session, employee_user, admin_client):
    """(b) Echo 07:45 (Rohstempel 07:00) auf den Dienstag verschoben: die
    Genehmigung rechnet mit dem Rohstempel und speichert 07:00 — dort beginnt
    schon ein Eintrag. Die alte Sonde prüfte 07:45."""
    employee_user.work_blocks = MON_TUE
    _db_session.commit()
    x = _entry(_db_session, employee_user, MON, time(7, 45), time(12, 0),
               raw_start_time=time(7, 0))
    _entry(_db_session, employee_user, TUE, time(7, 0), time(7, 30))
    cr = _cr(_db_session, employee_user, x, TUE, time(7, 45), time(12, 0))

    r = _approve(admin_client, cr)

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == DUP_DETAIL
    _assert_untouched(_db_session, cr, x, time(7, 45), time(7, 0))


def test_create_typed_start_clamped_onto_sibling_is_409(_db_session, employee_user, admin_client):
    """(c) Neuer Eintrag 07:30–09:00 wird auf 07:45 gekappt und fiele auf den
    Beginn eines bestehenden Eintrags."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    _entry(_db_session, employee_user, MON, time(7, 45), time(8, 30))
    cr = _cr(_db_session, employee_user, None, MON, time(7, 30), time(9, 0),
             rtype=ChangeRequestType.CREATE)

    r = _approve(admin_client, cr)

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == DUP_DETAIL
    _assert_untouched(_db_session, cr)
    assert _db_session.query(TimeEntry).filter(TimeEntry.date == MON).count() == 1


def test_create_without_blocks_exact_start_still_409(_db_session, employee_user, admin_client):
    """Unverändert: ohne Blöcke ist der gekappte Beginn der beantragte."""
    _entry(_db_session, employee_user, MON, time(8, 0), time(9, 0))
    cr = _cr(_db_session, employee_user, None, MON, time(8, 0), time(10, 0),
             rtype=ChangeRequestType.CREATE)

    r = _approve(admin_client, cr)

    assert r.status_code == 409, r.text
    _assert_untouched(_db_session, cr)


def test_update_echo_on_own_clamped_start_is_no_conflict(_db_session, employee_user, admin_client):
    """Die Sonde schliesst den Eintrag selbst aus: ein Antrag, der nur die
    Notiz ändert und die angerechnete Zeit zurückschickt, kollidiert nicht mit
    dem eigenen Beginn — auch nicht, wenn sie jetzt immer läuft."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    x = _entry(_db_session, employee_user, MON, time(7, 45), time(12, 0),
               raw_start_time=time(7, 0))
    cr = _cr(_db_session, employee_user, x, MON, time(7, 45), time(12, 0))

    r = _approve(admin_client, cr)

    assert r.status_code == 200, r.text
    _db_session.expire_all()
    stored = _db_session.get(TimeEntry, x.id)
    assert (stored.start_time, stored.raw_start_time) == (time(7, 45), time(7, 0))


def test_bulk_approve_reports_clamped_collision_per_item(_db_session, employee_user, admin_client):
    """Sammel-Genehmigung: der kollidierende Antrag wird als ``failed``
    gemeldet, der übrige genehmigt — kein 500 für den ganzen Aufruf."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    _entry(_db_session, employee_user, MON, time(7, 45), time(8, 30))
    clash = _cr(_db_session, employee_user, None, MON, time(7, 30), time(9, 0),
                rtype=ChangeRequestType.CREATE)
    fine = _cr(_db_session, employee_user, None, TUE, time(9, 0), time(12, 0),
               rtype=ChangeRequestType.CREATE)

    r = admin_client.post("/api/admin/change-requests/bulk-review", json={
        "request_ids": [str(clash.id), str(fine.id)], "action": "approve",
    })

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["succeeded"], body["failed"]) == (1, 1)
    items = {i["request_id"]: i for i in body["items"]}
    assert items[str(clash.id)]["status"] == "failed"
    assert items[str(clash.id)]["error"] == DUP_DETAIL
    assert items[str(fine.id)]["status"] == "approved"
