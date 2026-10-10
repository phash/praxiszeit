"""Spec 2026-10-08, 8.1 / P22 (PR2): die 24-Wochen-Auswertung führt neben der
angerechneten Zeit die Anwesenheit laut Stempel — die keine Neuberechnung senkt."""
import uuid
from datetime import time, timedelta

from app.models import TimeEntry
from app.models.tenant import Tenant
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON

URL = "/api/admin/reports/24-week-average?end_date=2026-06-05"


def _row(client, user):
    r = client.get(URL)
    assert r.status_code == 200, r.text
    return next(e for e in r.json()["employees"] if e["user_id"] == str(user.id))


def _add(db, user, d, start, end, **kw):
    e = TimeEntry(tenant_id=kw.pop("tenant_id", DEFAULT_TENANT_ID), user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def test_presence_next_to_credited_time(_db_session, employee_user, admin_client):
    _add(_db_session, employee_user, MON, time(8), time(18), uncredited_minutes=150)          # K1
    _add(_db_session, employee_user, MON + timedelta(days=1), time(7, 45), time(18, 15),
         raw_start_time=time(7), raw_end_time=time(19), uncredited_minutes=150)               # K7
    row = _row(admin_client, employee_user)
    assert row["total_hours"] == 15.5
    assert row["presence_hours"] == 22.0
    assert row["presence_average"] == round(22.0 / row["scheduled_work_days"], 2)


def test_retroactive_shortening_lowers_credited_not_presence(_db_session, employee_user, admin_client):
    e = _add(_db_session, employee_user, MON, time(8), time(18))
    before = _row(admin_client, employee_user)
    e.uncredited_minutes = 150   # wie eine spätere Neukappung (PR3)
    _db_session.commit()
    after = _row(admin_client, employee_user)
    assert after["total_hours"] == before["total_hours"] - 2.5
    assert after["presence_hours"] == before["presence_hours"] == 10.0


def test_weekly_presence_shows_a_week_over_48_hours(_db_session, employee_user, admin_client):
    """Spec 8.1/11.1 „je Woche" (P22, Pflicht 4): eine Woche mit 50 h laut Stempel
    bleibt im Bericht erkennbar, obwohl nur 37,5 h angerechnet sind (5 × K1)."""
    for i in range(5):
        _add(_db_session, employee_user, MON + timedelta(days=i), time(8), time(18), uncredited_minutes=150)
    row = _row(admin_client, employee_user)
    assert row["total_hours"] == 37.5
    assert row["presence_hours"] == 50.0
    assert row["presence_weeks"] == [{"iso_week": "2026-W23", "presence_hours": 50.0}]


def test_other_tenant_entries_do_not_count(_db_session, employee_user, admin_client):
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    _db_session.add(other)
    _db_session.commit()
    _add(_db_session, employee_user, MON, time(8), time(18), uncredited_minutes=150)
    _add(_db_session, employee_user, MON, time(19), time(21), tenant_id=other.id)
    row = _row(admin_client, employee_user)
    assert (row["total_hours"], row["presence_hours"]) == (7.5, 10.0)


def test_presence_weeks_ascending_and_edge_week_only_with_days_in_window(
    _db_session, employee_user, admin_client,
):
    """Fenster 19.12.2025 (Fr) bis 05.06.2026: die Randwoche 2025-W51 zählt nur den
    Freitag im Fenster, der Donnerstag davor fällt heraus; Wochen aufsteigend über
    den Jahreswechsel, offene Einträge zählen nicht."""
    from datetime import date
    _add(_db_session, employee_user, date(2025, 12, 18), time(8), time(18))   # vor dem Fenster
    _add(_db_session, employee_user, date(2025, 12, 19), time(8), time(12))   # 2025-W51
    _add(_db_session, employee_user, MON, time(8), time(17), break_minutes=60)  # 2026-W23
    _add(_db_session, employee_user, date(2026, 1, 2), time(7), time(9))      # 2026-W01
    _add(_db_session, employee_user, MON + timedelta(days=1), time(8), None)   # offen
    row = _row(admin_client, employee_user)
    assert row["presence_weeks"] == [
        {"iso_week": "2025-W51", "presence_hours": 4.0},
        {"iso_week": "2026-W01", "presence_hours": 2.0},
        {"iso_week": "2026-W23", "presence_hours": 8.0},
    ]
    assert row["presence_hours"] == 14.0


def test_auto_closed_presence_ends_at_effective_end(_db_session, employee_user, admin_client):
    """Spec 8.3 / P18: ein automatisch geschlossener Eintrag zählt bis zum wirksamen
    Ende, nie bis 23:59 — auch nicht über ein gespeichertes ``raw_end_time``."""
    _add(_db_session, employee_user, MON, time(8), time(18, 15),
         raw_end_time=time(23, 59), auto_closed=True)
    row = _row(admin_client, employee_user)
    assert row["presence_hours"] == 10.25
    assert row["presence_weeks"] == [{"iso_week": "2026-W23", "presence_hours": 10.25}]


def test_scheduled_days_respect_employment_window(_db_session, employee_user, admin_client):
    """#193: Tage vor ``first_work_day`` sind keine Soll-Arbeitstage. Eine
    Neueinstellung ab 25.05.2026 mit 10 × 10 h darf nicht über die 24 Wochen davor
    auf einen konformen Ø von unter einer Stunde verdünnt werden."""
    from datetime import date
    employee_user.first_work_day = date(2026, 5, 25)
    _db_session.commit()
    d = date(2026, 5, 25)
    while d <= date(2026, 6, 5):
        if d.weekday() < 5:
            _add(_db_session, employee_user, d, time(7), time(17))
        d += timedelta(days=1)
    row = _row(admin_client, employee_user)
    assert row["scheduled_work_days"] == 10
    assert row["average_daily_hours"] == 10.0
    assert row["presence_average"] == 10.0
    assert row["compliant"] is False


def test_scheduled_days_end_at_last_work_day(_db_session, employee_user, admin_client):
    """#193: Tage nach ``last_work_day`` zählen ebenfalls nicht als Soll-Arbeitstage."""
    from datetime import date
    employee_user.first_work_day = date(2026, 5, 25)
    employee_user.last_work_day = date(2026, 5, 29)
    _db_session.commit()
    row = _row(admin_client, employee_user)
    assert row["scheduled_work_days"] == 5
