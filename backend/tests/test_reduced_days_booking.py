"""Teil B (Task 5): Buchungspfade auf einem verkuerzten Tag.

24.12.2026 (Donnerstag) ist per Sondertage-Einstellung ``max_hours`` 4 h. Urlaub
kostet dort in JEDEM Buchungspfad 0,5 Tage (``half_special_day_weight``);
Betriebsferien buchen das verkuerzte Soll mit ``half_day=False``; der
Tagessoll-Endpoint wendet die Kappung an.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, User, UserRole
from app.models.system_setting import SystemSetting
from app.models.vacation_request import VacationRequest
from app.services import auth_service, calculation_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

D23 = date(2026, 12, 23)
D24 = date(2026, 12, 24)
PAST_D24 = date(2025, 12, 24)  # Änderungsanträge gibt es nur für vergangene Tage


def _client(db, user, admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(test_app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    test_app.dependency_overrides.clear()


def _set(db, key, value):
    db.add(SystemSetting(key=key, tenant_id=DEFAULT_TENANT_ID, value=value))
    db.commit()


@pytest.fixture
def d24_max4(db, default_tenant):
    _set(db, "special_day_dec24_mode", "max_hours")
    _set(db, "special_day_dec24_max_hours", "4")


def _mk_user(db, name, weekly_hours=40.0, vacation_days=30):
    u = User(
        id=uuid.uuid4(), username=name, email=f"{name}@t.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name=name, last_name="Test", role=UserRole.EMPLOYEE,
        weekly_hours=weekly_hours, vacation_days=vacation_days, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _used(db, user, year=2026):
    db.expire_all()
    return float(calculation_service.get_vacation_account(db, user, year)["used_days"])


def _absences(db, user):
    db.expire_all()
    return {a.date: a for a in db.query(Absence).filter(Absence.user_id == user.id).all()}


def test_create_absence_vacation_costs_half(db, d24_max4, test_user, test_admin):
    r = _client(db, test_user, test_admin).post("/api/absences", json={
        "date": D24.isoformat(), "type": "vacation", "hours": 8,
    })
    assert r.status_code == 201, r.text
    assert _absences(db, test_user)[D24].hours == 8.0
    assert _used(db, test_user) == 0.5


def test_vacation_request_approval_costs_half(db, d24_max4, test_user, test_admin):
    _set(db, "vacation_approval_required", "true")
    r = _client(db, test_user, test_admin).post("/api/vacation-requests/", json={
        "date": D24.isoformat(), "hours": 8,
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    r = _client(db, test_admin, test_admin).post(
        f"/api/admin/vacation-requests/{rid}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert D24 in _absences(db, test_user)
    assert _used(db, test_user) == 0.5


def test_change_request_vacation_costs_half(db, d24_max4, test_user, test_admin):
    r = _client(db, test_user, test_admin).post("/api/change-requests/", json={
        "request_type": "create", "entry_kind": "absence",
        "proposed_date": PAST_D24.isoformat(), "proposed_absence_type": "vacation",
        "proposed_absence_hours": 8, "reason": "Urlaub",
    })
    assert r.status_code in (200, 201), r.text
    r = _client(db, test_admin, test_admin).post(
        f"/api/admin/change-requests/{r.json()['id']}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert PAST_D24 in _absences(db, test_user)
    assert _used(db, test_user, 2025) == 0.5


def test_budget_check_counts_half(db, d24_max4, test_admin):
    emp = _mk_user(db, "halfbudget", vacation_days=0.5)
    client = _client(db, emp, test_admin)
    r = client.post("/api/absences", json={"date": D23.isoformat(), "type": "vacation", "hours": 8})
    assert r.status_code == 400, r.text
    r = client.post("/api/absences", json={"date": D24.isoformat(), "type": "vacation", "hours": 8})
    assert r.status_code == 201, r.text


def _vr(db, user, day):
    vr = VacationRequest(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=day, hours=8,
                         absence_type="vacation", status="pending")
    db.add(vr)
    db.commit()
    return vr


def test_vacation_request_create_budget_counts_half(db, d24_max4, test_admin):
    """F037: Budget-Vorprüfung beim Anlegen eines Urlaubsantrags (0,5 Tage Anspruch)."""
    _set(db, "vacation_approval_required", "true")
    emp = _mk_user(db, "vrcreate", vacation_days=0.5)
    client = _client(db, emp, test_admin)
    r = client.post("/api/vacation-requests/", json={"date": D23.isoformat(), "hours": 8})
    assert r.status_code == 400, r.text
    r = client.post("/api/vacation-requests/", json={"date": D24.isoformat(), "hours": 8})
    assert r.status_code == 201, r.text


def test_vacation_request_review_budget_counts_half(db, d24_max4, test_admin):
    """F037: Budget-Vorprüfung bei der GENEHMIGUNG (Antrag direkt angelegt, damit die
    Anlegeprüfung nicht vorher greift): 23.12. kostet 1, der 24.12. nur 0,5."""
    _set(db, "vacation_approval_required", "true")
    emp = _mk_user(db, "vrreview", vacation_days=0.5)
    over = _vr(db, emp, D23)
    fits = _vr(db, emp, D24)
    admin_client = _client(db, test_admin, test_admin)
    r = admin_client.post(f"/api/admin/vacation-requests/{over.id}/review", json={"action": "approve"})
    assert r.status_code == 400, r.text
    assert D23 not in _absences(db, emp)
    r = admin_client.post(f"/api/admin/vacation-requests/{fits.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert _used(db, emp) == 0.5


def test_change_request_review_budget_counts_half(db, d24_max4, test_admin):
    """F037: Budget-Prüfung der CR-Genehmigung (Absence-CREATE) am verkürzten Tag."""
    emp = _mk_user(db, "crbudget", vacation_days=0.5)
    past_d23 = date(2025, 12, 23)
    ids = {}
    for day in (past_d23, PAST_D24):
        r = _client(db, emp, test_admin).post("/api/change-requests/", json={
            "request_type": "create", "entry_kind": "absence",
            "proposed_date": day.isoformat(), "proposed_absence_type": "vacation",
            "proposed_absence_hours": 8, "reason": "Urlaub",
        })
        assert r.status_code in (200, 201), r.text
        ids[day] = r.json()["id"]
    admin_client = _client(db, test_admin, test_admin)
    r = admin_client.post(f"/api/admin/change-requests/{ids[past_d23]}/review", json={"action": "approve"})
    assert r.status_code == 400, r.text
    assert past_d23 not in _absences(db, emp)
    r = admin_client.post(f"/api/admin/change-requests/{ids[PAST_D24]}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert _used(db, emp, 2025) == 0.5


def test_request_day_count_half(db, d24_max4, test_user, test_admin):
    _set(db, "vacation_approval_required", "true")
    r = _client(db, test_user, test_admin).post("/api/vacation-requests/", json={
        "date": D24.isoformat(), "hours": 8,
    })
    assert r.status_code == 201, r.text
    r = _client(db, test_admin, test_admin).get("/api/admin/vacation-requests")
    assert r.status_code == 200, r.text
    mine = [x for x in r.json() if x["user_id"] == str(test_user.id)]
    assert [x["days"] for x in mine] == [0.5]


def test_closure_books_reduced_target(db, d24_max4, test_user, test_admin):
    short = _mk_user(db, "threehours", weekly_hours=15.0)
    r = _client(db, test_admin, test_admin).post("/api/company-closures/", json={
        "name": "BF", "start_date": "2026-12-21", "end_date": "2026-12-31",
        "counts_as_vacation": True,
    })
    assert r.status_code == 201, r.text
    full = _absences(db, test_user)
    assert full[D24].hours == 4.0
    assert full[D24].half_day is False
    assert full[D23].hours == 8.0
    assert _absences(db, short)[D24].hours == 3.0
    # 21.-23. + 25.-31. (ohne Wochenenden; im Test-Mandanten sind KEINE Feiertage
    # angelegt, 25./26.12. buchen also voll) voll, der 24.12. nur 0,5
    d24_cost = _used(db, test_user)
    only_d24 = sum(1 for a in full.values() if a.date != D24)
    assert d24_cost == only_d24 + 0.5


def test_closure_split_consistent(db, d24_max4, test_admin):
    def types(emp):
        a = _absences(db, emp)
        return [(d, a[d].type, a[d].hours) for d in sorted(a)]

    _set(db, "closure_overtime_after_vacation", "true")
    body = {"name": "BF", "start_date": D23.isoformat(), "end_date": D24.isoformat(),
            "counts_as_vacation": True}

    rich = _mk_user(db, "rich", vacation_days=1.5)
    poor = _mk_user(db, "poor", vacation_days=1)
    client = _client(db, test_admin, test_admin)
    r = client.post("/api/company-closures/", json=body)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    assert [(d, t) for d, t, _ in types(rich)] == [
        (D23, AbsenceType.VACATION), (D24, AbsenceType.VACATION)]
    assert [(d, t) for d, t, _ in types(poor)] == [
        (D23, AbsenceType.VACATION), (D24, AbsenceType.OVERTIME)]
    # F039: auch die Stunden — am verkürzten Tag das verkürzte Soll (4 h), nie 8 h.
    assert [h for _, _, h in types(rich)] == [8.0, 4.0]
    assert [h for _, _, h in types(poor)] == [8.0, 4.0]
    assert float(calculation_service.get_vacation_account(db, rich, 2026)["remaining_days"]) == 0

    before = {e.id: types(e) for e in (rich, poor)}
    r = client.put(f"/api/company-closures/{cid}", json=body)
    assert r.status_code == 200, r.text
    assert {e.id: types(e) for e in (rich, poor)} == before


def test_daily_target_endpoint_reduced(db, d24_max4, test_user, test_admin):
    client = _client(db, test_user, test_admin)
    r = client.get("/api/absences/daily-target", params={"date": "2026-12-24"})
    assert r.status_code == 200, r.text
    assert r.json()["hours"] == 4.0
    r = client.get("/api/absences/daily-target", params={"date": "2026-12-23"})
    assert r.status_code == 200, r.text
    assert r.json()["hours"] == 8.0
