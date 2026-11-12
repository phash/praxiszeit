"""calc-01 (R35): Jahresabschluss fuer kuenftige/laufende Jahre.

* kuenftiges Jahr -> 400
* laufendes Jahr -> 409 ohne ``confirm_open_year=true``, mit Flag erlaubt
* abgeschlossenes Jahr unveraendert
* ``GET /year-closing/{year}/preview`` nennt die Zahl manueller Uebertraege Y+1
"""
from datetime import date

from app.models import YearCarryover
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_year_closing_guards import (  # noqa: F401 (Fixtures)
    _app, _client_as, admin, db, default_tenant, emp,
)


def test_future_year_is_rejected(db, default_tenant, admin, emp):
    year = today_local().year + 1
    c = _client_as(db, admin)
    r = c.post(f"/api/admin/year-closing/{year}")
    r2 = c.post(f"/api/admin/year-closing/{year}?confirm_open_year=true")
    _app.dependency_overrides.clear()
    assert r.status_code == 400, r.text
    assert r2.status_code == 400, r2.text
    assert db.query(YearCarryover).count() == 0


def test_current_year_needs_confirmation(db, default_tenant, admin, emp):
    year = today_local().year
    c = _client_as(db, admin)
    r = c.post(f"/api/admin/year-closing/{year}")
    assert r.status_code == 409, r.text
    assert "noch nicht abgelaufen" in r.json()["detail"]
    assert db.query(YearCarryover).count() == 0
    r2 = c.post(f"/api/admin/year-closing/{year}?confirm_open_year=true")
    _app.dependency_overrides.clear()
    assert r2.status_code == 200, r2.text
    assert db.query(YearCarryover).filter(YearCarryover.year == year + 1).count() > 0


def test_past_year_needs_no_confirmation(db, default_tenant, admin, emp):
    r = _client_as(db, admin).post(f"/api/admin/year-closing/{today_local().year - 1}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text


def test_preview_counts_manual_carryovers(db, default_tenant, admin, emp):
    year = today_local().year
    db.add(YearCarryover(user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, year=year + 1,
                         overtime_hours=1, vacation_days=2, source="manual"))
    db.add(YearCarryover(user_id=admin.id, tenant_id=DEFAULT_TENANT_ID, year=year + 1,
                         overtime_hours=1, vacation_days=2, source="year_closing"))
    db.commit()
    c = _client_as(db, admin)
    cur = c.get(f"/api/admin/year-closing/{year}/preview").json()
    past = c.get(f"/api/admin/year-closing/{year - 1}/preview").json()
    fut = c.get(f"/api/admin/year-closing/{year + 1}/preview")
    _app.dependency_overrides.clear()
    assert cur == {"year": year, "next_year": year + 1, "is_open_year": True,
                   "manual_carryover_count": 1}
    assert past["is_open_year"] is False and past["manual_carryover_count"] == 0
    assert fut.status_code == 400
