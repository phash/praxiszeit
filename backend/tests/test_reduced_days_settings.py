"""Teil B Task 8: 24./31.12.-Einstellungen mit ``max_hours`` — Validierung und
automatisches Neubuchen der Betriebsferien."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, TimeEntryAuditLog, User, UserRole
from app.models.year_carryover import YearCarryover
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_reduced_days_router import _make_user

D24 = date(2026, 12, 24)
INVALID_MSG = "Die Stundenzahl muss zwischen 0,25 und 12 liegen (in Schritten von 0,25)."


@pytest.fixture
def client(db, test_admin):
    from app.routers import admin_settings, company_closures

    test_admin.receives_company_closures = False
    db.commit()
    app = FastAPI()
    app.include_router(admin_settings.router)
    app.include_router(company_closures.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: test_admin
    app.dependency_overrides[require_admin] = lambda: test_admin
    return TestClient(app)


@pytest.fixture
def employee(db, test_admin):
    return _make_user(db, DEFAULT_TENANT_ID, "emp1")


def _put(client, key, value):
    return client.put(f"/api/admin/settings/{key}", json={"value": value})


def _closure(client, start=date(2026, 12, 21), end=date(2026, 12, 31)):
    resp = client.post("/api/company-closures/", json={
        "name": "Winter", "start_date": start.isoformat(), "end_date": end.isoformat(),
    })
    assert resp.status_code == 201, resp.text


def _hours(db, user, d):
    db.expire_all()
    a = db.query(Absence).filter(Absence.user_id == user.id, Absence.date == d).first()
    return float(a.hours)


def test_put_max_hours_valid_and_readback(client):
    res = _put(client, "special_day_dec24_max_hours", "3.5")
    assert res.status_code == 200, res.text
    assert res.json()["value"] == "3.50"
    body = client.get("/api/admin/settings/special-days").json()
    assert body["special_day_dec24_max_hours"] == 3.5


@pytest.mark.parametrize("v", ["0", "12.5", "4.1", "x"])
def test_put_max_hours_invalid(client, v):
    res = _put(client, "special_day_dec31_max_hours", v)
    assert res.status_code == 400
    assert res.json()["detail"] == INVALID_MSG


def test_put_mode_max_hours_accepted(client):
    res = _put(client, "special_day_dec24_mode", "max_hours")
    assert res.status_code == 200, res.text
    assert res.json()["value"] == "max_hours"


def test_mode_change_resaves_closure(client, db, employee):
    _closure(client)
    assert _hours(db, employee, D24) == 8.0
    assert _put(client, "special_day_dec24_max_hours", "4").status_code == 200
    assert _hours(db, employee, D24) == 8.0  # Modus noch Arbeitstag
    assert _put(client, "special_day_dec24_mode", "max_hours").status_code == 200
    assert _hours(db, employee, D24) == 4.0


def test_hours_change_resaves_closure(client, db, employee):
    _closure(client)
    _put(client, "special_day_dec24_max_hours", "4")
    _put(client, "special_day_dec24_mode", "max_hours")
    assert _hours(db, employee, D24) == 4.0
    assert _put(client, "special_day_dec24_max_hours", "2").status_code == 200
    assert _hours(db, employee, D24) == 2.0


def test_hours_change_while_mode_working_day_noop(client, db, employee):
    _closure(client)
    audits = db.query(TimeEntryAuditLog).count()
    before = {(a.user_id, a.date, float(a.hours)) for a in db.query(Absence).all()}
    res = _put(client, "special_day_dec24_max_hours", "2")
    assert res.status_code == 200
    assert not res.json().get("warning")
    db.expire_all()
    assert {(a.user_id, a.date, float(a.hours)) for a in db.query(Absence).all()} == before
    assert db.query(TimeEntryAuditLog).count() == audits


def test_half_day_to_working_day_resaves(client, db, employee):
    _put(client, "special_day_dec24_mode", "half_day")
    _closure(client)
    assert _hours(db, employee, D24) == 4.0
    assert _put(client, "special_day_dec24_mode", "working_day").status_code == 200
    assert _hours(db, employee, D24) == 8.0


def test_closed_year_not_resaved(client, db, employee):
    _closure(client, start=date(2025, 12, 22), end=date(2025, 12, 30))
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, year=2026,
                         overtime_hours=0, vacation_days=0, source="year_closing"))
    db.commit()
    d = date(2025, 12, 24)
    assert _hours(db, employee, d) == 8.0
    res = _put(client, "special_day_dec24_mode", "half_day")
    assert res.status_code == 200, res.text
    assert _hours(db, employee, d) == 8.0
    assert "2025" in (res.json().get("warning") or "")
