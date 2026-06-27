"""#329: weekly admin report endpoint (GET /api/admin/reports/weekly).

Same response schema as /monthly (EmployeeMonthlyReport) but computed for an
ISO calendar week (Mon–Sun). week_start is normalised to the Monday of its week,
so a week crossing a month boundary works in one call.
"""
from datetime import date, time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import TimeEntry, Absence, AbsenceType
from tests.conftest import DEFAULT_TENANT_ID


def _reports_app() -> FastAPI:
    from app.routers import reports as reports_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit Weekly Report Test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(reports_router.router)
    return app


_app = _reports_app()

# A clearly-past week so the #313 "bis heute" cutoff never trims it:
# Mon 01.06.2026 .. Sun 07.06.2026.
WK_MON = date(2026, 6, 1)


def _entry(user, d, start=time(8, 0), end=time(17, 0), break_min=60):
    return TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                     start_time=start, end_time=end, break_minutes=break_min)


def _client(db, admin):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: admin
    _app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(_app)


def _row(resp, user):
    return next(r for r in resp.json() if r["user_id"] == str(user.id))


def test_weekly_report_basic(db, test_user, test_admin):
    db.add(_entry(test_user, WK_MON))                 # Mon 8h
    db.add(_entry(test_user, date(2026, 6, 2)))       # Tue 8h
    db.commit()
    try:
        client = _client(db, test_admin)
        r = client.get(f"/api/admin/reports/weekly?week_start={WK_MON.isoformat()}")
        assert r.status_code == 200, r.text
        row = _row(r, test_user)
        assert row["weekly_hours"] == 40.0
        assert row["target_hours"] == 40.0   # 5 workdays × 8h, full past week
        assert row["actual_hours"] == 16.0   # Mon+Tue
        assert row["balance"] == -24.0
    finally:
        _app.dependency_overrides.clear()


def test_weekly_report_normalises_non_monday(db, test_user, test_admin):
    # Passing a Wednesday must resolve to the same Mon–Sun week.
    db.add(_entry(test_user, WK_MON))
    db.commit()
    try:
        client = _client(db, test_admin)
        wed = date(2026, 6, 3)
        r = client.get(f"/api/admin/reports/weekly?week_start={wed.isoformat()}")
        assert r.status_code == 200, r.text
        assert _row(r, test_user)["actual_hours"] == 8.0
    finally:
        _app.dependency_overrides.clear()


def test_weekly_report_spans_month_boundary(db, test_user, test_admin):
    # Mon 29.06. .. Sun 05.07. → target spans June+July (5 workdays = 40h).
    # This week is in the future relative to "today"; use soll_basis=monatsende
    # so the #313 bis_heute cutoff doesn't trim it (which is itself correct).
    db.add(_entry(test_user, date(2026, 6, 30)))   # Tue 8h (June)
    db.add(_entry(test_user, date(2026, 7, 1)))    # Wed 8h (July)
    db.commit()
    try:
        client = _client(db, test_admin)
        r = client.get("/api/admin/reports/weekly?week_start=2026-06-29&soll_basis=monatsende")
        assert r.status_code == 200, r.text
        row = _row(r, test_user)
        assert row["target_hours"] == 40.0
        assert row["actual_hours"] == 16.0
    finally:
        _app.dependency_overrides.clear()


def test_weekly_report_vacation_reduces_target_and_counts_days(db, test_user, test_admin):
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 6, 2),
                   type=AbsenceType.VACATION, hours=8.0))
    db.commit()
    try:
        client = _client(db, test_admin)
        r = client.get(f"/api/admin/reports/weekly?week_start={WK_MON.isoformat()}")
        assert r.status_code == 200, r.text
        row = _row(r, test_user)
        assert row["target_hours"] == 32.0          # 5 workdays − 1 vacation day
        assert row["vacation_used_days"] == pytest.approx(1.0)
    finally:
        _app.dependency_overrides.clear()


def test_weekly_report_sick_masked_without_flag(db, test_user, test_admin):
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 6, 3),
                   type=AbsenceType.SICK, hours=8.0))
    db.commit()
    try:
        client = _client(db, test_admin)
        r1 = client.get(f"/api/admin/reports/weekly?week_start={WK_MON.isoformat()}")
        assert _row(r1, test_user)["sick_days"] == 0.0   # DSGVO Art. 9
        r2 = client.get(f"/api/admin/reports/weekly?week_start={WK_MON.isoformat()}&include_health_data=true")
        assert _row(r2, test_user)["sick_days"] == pytest.approx(1.0)
    finally:
        _app.dependency_overrides.clear()


def test_weekly_report_invalid_week_start(db, test_admin):
    try:
        client = _client(db, test_admin)
        r = client.get("/api/admin/reports/weekly?week_start=not-a-date")
        assert r.status_code == 400
    finally:
        _app.dependency_overrides.clear()
