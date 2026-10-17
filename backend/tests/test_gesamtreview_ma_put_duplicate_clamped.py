"""Gesamtreview 1.20 (Review-Fund 2, Rest): ``PUT /api/time-entries/{id}``
prüft Duplikate auf dem GEKAPPTEN Beginn.

Die MA-Route (Mitarbeitende für heute, Admins über die Zeiterfassung für jeden
Tag) übernimmt Beginn und Datum, kappt und schreibt ``clamp(...).eff_start``
(beim Datumswechsel E39 auch ohne neuen Beginn). Ob ein anderer Eintrag des
Tages schon diesen Beginn hat, prüfte sie gar nicht — erst der Index
``uq_tenant_user_date_start`` schlug zu (IntegrityError, auf PG HTTP 500).
Alle Geschwisterpfade antworten dort mit 409: ``create_time_entry`` (Release-
Review 1.16.0), ``admin_create/update_time_entry`` (#375-Review) und die
Antragsgenehmigung (Gesamtreview B2).
"""
from datetime import date, time

import pytest

from app.models import TimeEntry
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

TUE = date(2026, 6, 2)
# Mo wie K_BLOCKS (Hülle 07:45–18:15), Di 07:00–12:00 (Hülle 06:45–12:15).
MON_TUE = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("07:00", "12:00")])

DUP_DETAIL = "Es existiert bereits ein Eintrag mit dieser Startzeit an diesem Datum"


def _entry(db, user, d, start, end, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=0, **kw)
    db.add(e)
    db.commit()
    return e


@pytest.fixture
def today_monday(monkeypatch):
    import app.routers.time_entries as te
    monkeypatch.setattr(te, "_today_local", lambda: MON)


def _assert_untouched(db, entry, d, start, raw_start):
    db.expire_all()
    stored = db.get(TimeEntry, entry.id)
    assert stored.date == d
    assert stored.start_time == start
    assert stored.raw_start_time == raw_start


def test_employee_start_clamped_onto_sibling_is_409(
    _db_session, employee_user, employee_client, today_monday,
):
    """(d) Beginn 07:40 liegt vor der Hülle und wird auf 07:45 gekappt —
    dort beginnt schon ein anderer Eintrag des Tages."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    _entry(_db_session, employee_user, MON, time(7, 45), time(8, 30),
           raw_start_time=time(7, 38))
    b = _entry(_db_session, employee_user, MON, time(9, 30), time(12, 0))

    r = employee_client.put(f"/api/time-entries/{b.id}", json={
        "date": MON.isoformat(), "start_time": "07:40", "end_time": "12:00",
        "break_minutes": 0,
    })

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == DUP_DETAIL
    _assert_untouched(_db_session, b, MON, time(9, 30), None)


def test_employee_exact_sibling_start_is_409(
    _db_session, employee_user, employee_client, today_monday,
):
    """Ohne Blöcke: derselbe Beginn wie ein anderer Eintrag des Tages."""
    _entry(_db_session, employee_user, MON, time(8, 0), time(9, 0))
    b = _entry(_db_session, employee_user, MON, time(10, 0), time(11, 0))

    r = employee_client.put(f"/api/time-entries/{b.id}", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "11:00",
        "break_minutes": 0,
    })

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == DUP_DETAIL
    _assert_untouched(_db_session, b, MON, time(10, 0), None)


def test_admin_date_change_recaps_onto_sibling_is_409(
    _db_session, employee_user, admin_client,
):
    """E39: eine Admin verschiebt auf der MA-Route nur das Datum. Die
    Neukappung rechnet mit dem Rohstempel 07:00 und speichert am Dienstag
    07:00 — dort beginnt schon ein Eintrag."""
    employee_user.work_blocks = MON_TUE
    _db_session.commit()
    x = _entry(_db_session, employee_user, MON, time(7, 45), time(12, 0),
               raw_start_time=time(7, 0))
    _entry(_db_session, employee_user, TUE, time(7, 0), time(7, 30))

    r = admin_client.put(f"/api/time-entries/{x.id}", json={"date": TUE.isoformat()})

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == DUP_DETAIL
    _assert_untouched(_db_session, x, MON, time(7, 45), time(7, 0))


def test_own_start_unchanged_is_not_a_duplicate(
    _db_session, employee_user, employee_client, today_monday,
):
    """Kontrolle: der eigene Beginn ist kein Duplikat (``id != entry.id``)."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(7, 45), time(12, 0),
               raw_start_time=time(7, 30))

    r = employee_client.put(f"/api/time-entries/{e.id}", json={
        "date": MON.isoformat(), "start_time": "07:45", "end_time": "12:00",
        "break_minutes": 0, "note": "nur Notiz",
    })

    assert r.status_code == 200, r.text
    _db_session.expire_all()
    stored = _db_session.get(TimeEntry, e.id)
    assert stored.note == "nur Notiz"
    assert stored.raw_start_time == time(7, 30)
