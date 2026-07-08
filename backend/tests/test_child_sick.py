"""#376 Kind krank / unpaid_free-Gründe: Verhalten, Zähler, weiche §45-Warnung.

Nutzt das repo-übliche Test-Muster: lokal gebaute FastAPI-App +
``dependency_overrides`` (get_db/get_current_user/require_admin), headerloser
TestClient, alle Pfade mit ``/api``-Prefix (kein Header-Auth, keine
``client``/``admin_headers``-Fixtures — die existieren nicht).
"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType, AbsenceReason
from app.models.absence import AbsenceReasonBehavior, BEHAVIOR_TO_ABSENCE_TYPE
from app.models.tenant import Tenant
from app.services import auth_service, calculation_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

ADMIN_REASONS = "/api/admin/absence-reasons"
ABSENCES = "/api/absences/"
SETTINGS = "/api/admin/settings"
USERS = "/api/admin/users"
CHANGE_REQUESTS = "/api/change-requests/"
ADMIN_CR = "/api/admin/change-requests"

MON = date(2026, 3, 2)   # Montag, Vergangenheit (< heute), Werktag, kein Feiertag
TUE = date(2026, 3, 3)
WED = date(2026, 3, 4)


def _app() -> FastAPI:
    from app.routers import absence_reasons, absences, admin, change_requests
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    a = FastAPI()
    limiter.enabled = False
    a.state.limiter = limiter
    a.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    a.include_router(absence_reasons.admin_router)
    a.include_router(absence_reasons.read_router)
    a.include_router(absences.router)
    a.include_router(admin.router)
    a.include_router(change_requests.router)
    return a


app = _app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="D", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, username, role=UserRole.EMPLOYEE):
    u = User(
        username=username, email=f"{username}@x.de",
        password_hash=auth_service.hash_password("test123"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "admin1", role=UserRole.ADMIN)


@pytest.fixture
def employee(db, default_tenant):
    return _user(db, "emp1")


def _client_as(db, user, admin_user):
    def od():
        yield db
    app.dependency_overrides[get_db] = od
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


@pytest.fixture
def admin_client(db, admin):
    c = _client_as(db, admin, admin)
    yield c
    app.dependency_overrides.clear()


def _mk_reason_row(db, tracks, name="Kind krank"):
    r = AbsenceReason(
        tenant_id=DEFAULT_TENANT_ID, name=name, base_behavior="unpaid_free",
        is_active=True, tracks_child_sick_limit=tracks,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# --------------------------------------------------------------------------- #
# Pure model/schema
# --------------------------------------------------------------------------- #
def test_unpaid_free_behavior_maps_to_other():
    assert AbsenceReasonBehavior.UNPAID_FREE.value == "unpaid_free"
    assert BEHAVIOR_TO_ABSENCE_TYPE[AbsenceReasonBehavior.UNPAID_FREE] == AbsenceType.OTHER


def test_new_columns_exist_with_defaults():
    assert "tracks_child_sick_limit" in AbsenceReason.__table__.columns
    assert AbsenceReason.__table__.columns["tracks_child_sick_limit"].nullable is False
    assert "child_sick_days_per_year" in User.__table__.columns
    assert User.__table__.columns["child_sick_days_per_year"].nullable is True


def test_schema_fields_present():
    from app.schemas.absence_reason import AbsenceReasonCreate, AbsenceReasonResponse
    from app.schemas.absence import AbsenceResponse
    c = AbsenceReasonCreate(name="Kind krank", base_behavior="unpaid_free", tracks_child_sick_limit=True)
    assert c.tracks_child_sick_limit is True
    assert "tracks_child_sick_limit" in AbsenceReasonResponse.model_fields
    assert "warnings" in AbsenceResponse.model_fields


# --------------------------------------------------------------------------- #
# Router: persist flag + setting
# --------------------------------------------------------------------------- #
def test_create_reason_persists_child_sick_flag(admin_client):
    resp = admin_client.post(ADMIN_REASONS, json={
        "name": "Kind krank", "base_behavior": "unpaid_free", "tracks_child_sick_limit": True,
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tracks_child_sick_limit"] is True
    assert body["base_behavior"] == "unpaid_free"


def test_child_sick_days_default_setting_accepts_int(admin_client):
    ok = admin_client.put(f"{SETTINGS}/child_sick_days_default", json={"value": "20"})
    assert ok.status_code == 200, ok.text
    bad = admin_client.put(f"{SETTINGS}/child_sick_days_default", json={"value": "-3"})
    assert bad.status_code == 400


# --------------------------------------------------------------------------- #
# Calc helpers (pure)
# --------------------------------------------------------------------------- #
def test_child_sick_cap_prefers_user_then_setting_then_15(db, employee):
    assert calculation_service.child_sick_cap(db, employee) == 15  # kein Feld, kein Setting
    employee.child_sick_days_per_year = 22
    db.commit()
    assert calculation_service.child_sick_cap(db, employee) == 22  # per-MA schlägt alles


def test_child_sick_days_used_counts_only_flagged_reason_tagebasiert(db, employee):
    flagged = _mk_reason_row(db, True, name="Kind krank")
    other = _mk_reason_row(db, False, name="Unbezahlt sonstig")
    db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, date=MON,
                   type=AbsenceType.OTHER, hours=8, half_day=False, reason_id=flagged.id))
    db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, date=TUE,
                   type=AbsenceType.OTHER, hours=8, half_day=True, reason_id=flagged.id))
    db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, date=WED,
                   type=AbsenceType.OTHER, hours=8, half_day=False, reason_id=other.id))
    db.commit()
    assert calculation_service.child_sick_days_used(db, employee, 2026) == Decimal("1.5")
    assert calculation_service.child_sick_days_used(db, employee, 2025) == Decimal("0")


# --------------------------------------------------------------------------- #
# Weiche Warnung: create_absence
# --------------------------------------------------------------------------- #
def test_child_sick_over_cap_warns_but_books(db, admin, employee):
    client = _client_as(db, admin, admin)
    # Cap = 1 Tag
    r = client.put(f"{USERS}/{employee.id}", json={"child_sick_days_per_year": 1})
    assert r.status_code == 200, r.text
    reason_id = client.post(ADMIN_REASONS, json={
        "name": "Kind krank", "base_behavior": "unpaid_free", "tracks_child_sick_limit": True,
    }).json()["id"]

    r1 = client.post(ABSENCES, json={
        "user_id": str(employee.id), "date": str(MON), "type": "other", "hours": 8, "reason_id": reason_id})
    assert r1.status_code == 201, r1.text
    assert not any("CHILD_SICK_LIMIT" in w for a in r1.json() for w in a["warnings"])

    r2 = client.post(ABSENCES, json={
        "user_id": str(employee.id), "date": str(TUE), "type": "other", "hours": 8, "reason_id": reason_id})
    assert r2.status_code == 201, r2.text
    assert any("CHILD_SICK_LIMIT" in w for a in r2.json() for w in a["warnings"])
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Weiche Warnung: CR-Genehmigung (paralleler Buchungspfad)
# --------------------------------------------------------------------------- #
def test_child_sick_warning_in_cr_approval(db, admin, employee):
    admin_c = _client_as(db, admin, admin)
    admin_c.put(f"{USERS}/{employee.id}", json={"child_sick_days_per_year": 0})  # Cap 0 → jede Buchung > Limit
    reason_id = admin_c.post(ADMIN_REASONS, json={
        "name": "Kind krank", "base_behavior": "unpaid_free", "tracks_child_sick_limit": True,
    }).json()["id"]

    # MA stellt Absence-Änderungsantrag (CREATE) mit dem Grund
    emp_c = _client_as(db, employee, admin)
    cr = emp_c.post(CHANGE_REQUESTS, json={
        "entry_kind": "absence", "request_type": "create", "proposed_date": str(MON),
        "proposed_absence_type": "other", "proposed_absence_hours": 8,
        "reason_id": reason_id, "reason": "Kind krank",
    })
    assert cr.status_code == 201, cr.text
    cr_id = cr.json()["id"]

    # Admin genehmigt (4-Augen: Autor=MA, Genehmiger=Admin)
    admin_c2 = _client_as(db, admin, admin)
    resp = admin_c2.post(f"{ADMIN_CR}/{cr_id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    assert any("CHILD_SICK_LIMIT" in w for w in resp.json()["warnings"])
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# users-overview
# --------------------------------------------------------------------------- #
def test_users_overview_includes_child_sick(db, admin, employee):
    client = _client_as(db, admin, admin)
    client.put(f"{USERS}/{employee.id}", json={"child_sick_days_per_year": 12})
    rows = client.get(f"{USERS}-overview").json()
    row = next(r for r in rows if r["user_id"] == str(employee.id))
    assert row["child_sick_cap"] == 12
    assert row["child_sick_used"] == 0
    app.dependency_overrides.clear()
