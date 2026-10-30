"""Gesamtreview 1.20 B6 (PR2 Task 17): ``GET /api/time-entries/day-blocks?date=``
liefert die Arbeitszeit-Blöcke und den Puffer eines BELIEBIGEN Tages der
eigenen Person.

Die §4-Vorprüfung und die Pausen-Automatik der Zeiterfassung kannten nur die
Blöcke von heute (``/clock-status``); an jedem anderen Tag rechneten sie ohne
Blöcke. Bei einem geteilten Dienst (Lücke zwischen den Blöcken deckt §4) sperrte
das Formular deshalb fälschlich bzw. zog zusätzlich zur Lücke 30 Min Pause ab —
etwa wenn die Verwaltung ihren eigenen Eintrag eines vergangenen Tages erfasst
oder das Datum eines Eintrags ändert. Der Server kappt dort ohnehin mit den
Blöcken des Zieldatums; das Formular braucht dieselbe Grundlage.
"""
from datetime import date, timedelta

from app.models import PublicHoliday
from app.models.system_setting import SystemSetting
from app.models.working_hours_change import WorkingHoursChange
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON, block_week

TUE = date(2026, 6, 2)
SAT = date(2026, 6, 6)
WEEK = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "13:00")])
LATER = block_week(mon=[("09:00", "13:00")])
MON_BLOCKS = [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}]


def _day(client, d):
    r = client.get(f"/api/time-entries/day-blocks?date={d.isoformat()}")
    assert r.status_code == 200, r.text
    return r.json()


def test_blocks_and_tenant_grace_of_the_requested_day(_db_session, employee_user, employee_client):
    employee_user.work_blocks = WEEK
    _db_session.add(SystemSetting(key="work_window_grace_minutes", value="10", tenant_id=DEFAULT_TENANT_ID))
    _db_session.commit()

    body = _day(employee_client, MON)
    assert body == {"date": MON.isoformat(), "blocks": MON_BLOCKS, "blockless_workday": False, "grace_minutes": 10}
    assert _day(employee_client, TUE)["blocks"] == [{"start": "08:00", "end": "13:00"}]


def test_past_day_uses_the_snapshot_valid_on_that_day(_db_session, employee_user, employee_client):
    """#431/Spec 9.8: datumsaufgelöst — eine später wirksame Änderung gilt für
    den vergangenen Montag nicht, für den Montag danach schon."""
    employee_user.work_blocks = WEEK
    _db_session.add(WorkingHoursChange(
        user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=MON + timedelta(days=1), weekly_hours=4,
        use_daily_schedule=False, work_days_per_week=1, blocks=LATER,
    ))
    _db_session.commit()

    assert _day(employee_client, MON)["blocks"] == MON_BLOCKS
    assert _day(employee_client, MON + timedelta(days=7))["blocks"] == [{"start": "09:00", "end": "13:00"}]


def test_no_blocks_on_weekend_holiday_and_without_hour_tracking(_db_session, employee_user, employee_client):
    employee_user.work_blocks = WEEK
    _db_session.add(PublicHoliday(tenant_id=DEFAULT_TENANT_ID, date=TUE, name="Testfeiertag", year=TUE.year))
    _db_session.commit()
    invalidate_holiday_cache()  # F-034: ein früherer Test kann 2026 ohne Feiertag gecacht haben
    try:
        assert _day(employee_client, SAT)["blocks"] == []
        assert _day(employee_client, TUE)["blocks"] == []
        employee_user.track_hours = False
        _db_session.commit()
        assert _day(employee_client, MON)["blocks"] == []
    finally:
        invalidate_holiday_cache()


def test_without_work_blocks_empty_list_and_default_grace(employee_client):
    body = _day(employee_client, MON)
    assert body["blocks"] == []
    assert body["grace_minutes"] == 15


def test_only_the_own_schedule(_db_session, employee_user, admin_user, admin_client):
    """Kein ``user_id``-Parameter: die Verwaltung bekommt ihre EIGENEN Blöcke,
    nie die einer anderen Person (die Zeiterfassung ist die eigene Ansicht)."""
    employee_user.work_blocks = WEEK
    _db_session.commit()
    assert _day(admin_client, MON)["blocks"] == []
    r = admin_client.get(f"/api/time-entries/day-blocks?date={MON.isoformat()}&user_id={employee_user.id}")
    assert r.status_code == 200
    assert r.json()["blocks"] == []


def test_invalid_or_missing_date_is_422(employee_client):
    assert employee_client.get("/api/time-entries/day-blocks").status_code == 422
    assert employee_client.get("/api/time-entries/day-blocks?date=kein-datum").status_code == 422
