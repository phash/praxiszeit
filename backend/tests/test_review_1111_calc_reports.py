"""Code-Review 2026-11-11, Slice calc: calc-05/06/07/13 (Berichte)."""
from datetime import date, time

import pytest

from app.models import Absence, AbsenceType, TimeEntry
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_weekly_report import WK_MON, _app, _client, _entry, _row


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _app.dependency_overrides.clear()


# --- calc-05: §11-Sonntage nur im Beschaeftigungsfenster --------------------

def test_sunday_summary_counts_only_employment_window(db, test_user, test_admin):
    test_user.first_work_day = date(2026, 12, 1)
    for d in (6, 13, 20, 27):  # alle vier Dezember-Sonntage 2026
        db.add(_entry(test_user, date(2026, 12, d)))
    db.add(_entry(test_user, date(2026, 11, 29)))  # Sonntag VOR Eintritt: zaehlt nicht
    db.commit()
    r = _client(db, test_admin).get("/api/admin/reports/sunday-summary?year=2026")
    assert r.status_code == 200, r.text
    row = next(e for e in r.json()["employees"] if e["user_id"] == str(test_user.id))
    assert row["total_sundays_in_year"] == 4
    assert row["sundays_worked"] == 4
    assert row["free_sundays"] == 0
    assert row["partial_year"] is True
    assert row["compliant"] is False


def test_sunday_summary_full_year_unchanged(db, test_user, test_admin):
    test_user.first_work_day = None
    test_user.last_work_day = None
    db.commit()
    r = _client(db, test_admin).get("/api/admin/reports/sunday-summary?year=2026")
    row = next(e for e in r.json()["employees"] if e["user_id"] == str(test_user.id))
    assert row["total_sundays_in_year"] == 52
    assert row["partial_year"] is False
    assert row["compliant"] is True


# --- calc-06: min_rest_hours --------------------------------------------------

@pytest.mark.parametrize("val", ["0", "-3", "25"])
def test_rest_violations_rejects_out_of_range(db, test_admin, val):
    r = _client(db, test_admin).get(f"/api/admin/reports/rest-time-violations?year=2026&min_rest_hours={val}")
    assert r.status_code == 422


def test_rest_violations_reports_used_value(db, test_admin):
    c = _client(db, test_admin)
    assert c.get("/api/admin/reports/rest-time-violations?year=2026").json()["min_rest_hours"] == 11
    assert c.get("/api/admin/reports/rest-time-violations?year=2026&min_rest_hours=13").json()["min_rest_hours"] == 13


# --- calc-07: Urlaub/Krank in Monats- und Wochenbericht gleich gezaehlt -------

def test_future_vacation_counted_equally_in_week_and_month(db, test_user, test_admin, monkeypatch):
    monkeypatch.setattr(calculation_service, "get_soll_cutoff_date", lambda db_, u: date(2026, 6, 2))
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 6, 4),
                   type=AbsenceType.VACATION, hours=8.0))
    db.commit()
    c = _client(db, test_admin)
    wk = _row(c.get(f"/api/admin/reports/weekly?week_start={WK_MON.isoformat()}"), test_user)
    mo = _row(c.get("/api/admin/reports/monthly?month=2026-06"), test_user)
    assert wk["vacation_used_days"] == pytest.approx(1.0)
    assert mo["vacation_used_days"] == pytest.approx(1.0)


def test_absence_outside_employment_window_not_counted(db, test_user, test_admin):
    test_user.first_work_day = date(2026, 6, 3)
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 6, 2),
                   type=AbsenceType.VACATION, hours=8.0))
    db.commit()
    c = _client(db, test_admin)
    wk = _row(c.get(f"/api/admin/reports/weekly?week_start={WK_MON.isoformat()}"), test_user)
    mo = _row(c.get("/api/admin/reports/monthly?month=2026-06"), test_user)
    assert wk["vacation_used_days"] == 0.0
    assert mo["vacation_used_days"] == 0.0


# --- calc-13: Ausgeschiedene mit Daten erscheinen in den Bildschirmberichten --

def test_departed_user_with_data_in_screen_reports(db, test_user, test_admin):
    test_user.is_active = False
    db.add(_entry(test_user, date(2026, 6, 2)))
    db.commit()
    c = _client(db, test_admin)
    assert _row(c.get("/api/admin/reports/monthly?month=2026-06"), test_user)
    assert _row(c.get(f"/api/admin/reports/weekly?week_start={WK_MON.isoformat()}"), test_user)
    y = c.get("/api/admin/reports/yearly-absences?year=2026").json()
    assert any(r["user_id"] == str(test_user.id) for r in y)


def test_departed_user_without_data_stays_out(db, test_user, test_admin):
    test_user.is_active = False
    db.commit()
    c = _client(db, test_admin)
    assert not any(r["user_id"] == str(test_user.id) for r in c.get("/api/admin/reports/monthly?month=2026-06").json())
