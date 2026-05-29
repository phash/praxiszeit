"""
Cross-tenant API isolation tests.

These tests verify the APPLICATION-LAYER tenant scoping that sits on top of
PostgreSQL RLS. RLS-level isolation is covered by test_tenant_rls.py against
a real Postgres; these tests run on SQLite and exercise the explicit
`tenant_id == current_user.tenant_id` filters that CLAUDE.md mandates as
belt-and-suspenders defence (F-026).

Goal: a user authenticated as a member of Tenant A must never be able to
read, update, or delete data owned by Tenant B — even when they guess or
scrape the UUID of a Tenant B resource.
"""

import uuid
import pytest
from datetime import date, time, timedelta, datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TimeEntry, ChangeRequest, ChangeRequestStatus, ChangeRequestType
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app

TENANT_A_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
TENANT_B_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")


@pytest.fixture(scope="function")
def _db_session():
    """Fresh SQLite session per test."""
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.commit()
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.commit()
        Base.metadata.drop_all(bind=engine, checkfirst=True)


@pytest.fixture(scope="function")
def two_tenants(_db_session):
    """Create two isolated tenants."""
    for tid, name in [(TENANT_A_ID, "Tenant A"), (TENANT_B_ID, "Tenant B")]:
        _db_session.add(Tenant(id=tid, name=name, slug=f"t-{tid.hex[:8]}", is_active=True, mode="multi"))
    _db_session.commit()
    return TENANT_A_ID, TENANT_B_ID


def _make_user(db, tenant_id, *, role=UserRole.EMPLOYEE, username=None):
    u = User(
        username=username or f"user_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@test.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Test",
        last_name="User",
        role=role,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture(scope="function")
def admin_a(_db_session, two_tenants):
    return _make_user(_db_session, TENANT_A_ID, role=UserRole.ADMIN, username="admin_a")


@pytest.fixture(scope="function")
def employee_b(_db_session, two_tenants):
    return _make_user(_db_session, TENANT_B_ID, role=UserRole.EMPLOYEE, username="employee_b")


@pytest.fixture(scope="function")
def admin_b(_db_session, two_tenants):
    return _make_user(_db_session, TENANT_B_ID, role=UserRole.ADMIN, username="admin_b")


@pytest.fixture(scope="function")
def client_as_admin_a(_db_session, admin_a):
    """Authenticated as admin of Tenant A."""
    def _override_db():
        yield _db_session

    def _current():
        return admin_a

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _current
    test_app.dependency_overrides[require_admin] = _current

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


# ─── Tests ──────────────────────────────────────────────────────────────


def test_admin_a_cannot_read_tenant_b_user(_db_session, client_as_admin_a, employee_b):
    """GET /admin/users/{tenant_b_user_id} — must return 404 from _get_user_in_tenant (F-026)."""
    resp = client_as_admin_a.get(f"/api/admin/users/{employee_b.id}")
    assert resp.status_code == 404, resp.text


def test_admin_a_cannot_update_tenant_b_user(_db_session, client_as_admin_a, employee_b):
    """PUT /admin/users/{tenant_b_user_id} — must return 404 before mutation."""
    resp = client_as_admin_a.put(
        f"/api/admin/users/{employee_b.id}",
        json={"first_name": "Compromised"},
    )
    assert resp.status_code == 404, resp.text

    # Verify the victim's name was NOT changed
    _db_session.expire_all()
    victim = _db_session.query(User).filter(User.id == employee_b.id).first()
    assert victim.first_name == "Test"


def test_admin_a_cannot_deactivate_tenant_b_user(_db_session, client_as_admin_a, employee_b):
    """POST /admin/users/{tenant_b_user_id}/deactivate — must not touch victim."""
    resp = client_as_admin_a.post(f"/api/admin/users/{employee_b.id}/deactivate")
    assert resp.status_code == 404, resp.text

    _db_session.expire_all()
    victim = _db_session.query(User).filter(User.id == employee_b.id).first()
    assert victim.is_active is True


def test_admin_a_cannot_reset_tenant_b_user_password(_db_session, client_as_admin_a, employee_b):
    """POST /admin/users/{tenant_b_user_id}/set-password — must not succeed."""
    original_hash = employee_b.password_hash
    resp = client_as_admin_a.post(
        f"/api/admin/users/{employee_b.id}/set-password",
        json={"password": "AttackerKnows2025!"},
    )
    assert resp.status_code == 404, resp.text

    _db_session.expire_all()
    victim = _db_session.query(User).filter(User.id == employee_b.id).first()
    assert victim.password_hash == original_hash


def test_admin_a_cannot_approve_tenant_b_change_request(_db_session, client_as_admin_a, employee_b):
    """
    POST /admin/change-requests/{cr_id}/review — tenant filter in the review
    query (admin_change_requests.py:95) must make Tenant B's CR invisible to
    Tenant A's admin, even when the CR id is known.
    """
    cr = ChangeRequest(
        id=uuid.uuid4(),
        user_id=employee_b.id,
        tenant_id=TENANT_B_ID,
        request_type=ChangeRequestType.CREATE,
        status=ChangeRequestStatus.PENDING,
        proposed_date=date.today(),
        proposed_start_time=time(8, 0),
        proposed_end_time=time(16, 0),
        proposed_break_minutes=30,
        reason="test",
        entry_kind="time_entry",
    )
    _db_session.add(cr)
    _db_session.commit()

    resp = client_as_admin_a.post(
        f"/api/admin/change-requests/{cr.id}/review",
        json={"action": "approve"},
    )
    assert resp.status_code == 404, resp.text

    _db_session.expire_all()
    stored = _db_session.query(ChangeRequest).filter(ChangeRequest.id == cr.id).first()
    assert stored.status == ChangeRequestStatus.PENDING


@pytest.fixture(scope="function")
def employee_a(_db_session, two_tenants):
    return _make_user(_db_session, TENANT_A_ID, role=UserRole.EMPLOYEE, username="employee_a")


@pytest.fixture(scope="function")
def client_as_employee_a(_db_session, employee_a):
    """Authenticated as a regular employee of Tenant A (non-admin endpoints)."""
    def _override_db():
        yield _db_session

    def _current():
        return employee_a

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _current

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


# ─── Phase 0: belt-and-suspenders filter coverage for the 6 endpoints fixed
#     in feat/phase0-tenant-isolation. Each test creates data in BOTH tenants
#     and verifies that the response only ever contains Tenant A data.

def test_admin_users_list_excludes_tenant_b(_db_session, client_as_admin_a, admin_a, employee_b):
    """GET /admin/users — must not include Tenant B users."""
    resp = client_as_admin_a.get("/api/admin/users")
    assert resp.status_code == 200, resp.text
    ids = {u["id"] for u in resp.json()}
    assert str(admin_a.id) in ids
    assert str(employee_b.id) not in ids


def _make_pending_cr(db, user, tenant_id):
    cr = ChangeRequest(
        id=uuid.uuid4(),
        user_id=user.id,
        tenant_id=tenant_id,
        request_type=ChangeRequestType.CREATE,
        status=ChangeRequestStatus.PENDING,
        proposed_date=date.today(),
        proposed_start_time=time(8, 0),
        proposed_end_time=time(16, 0),
        proposed_break_minutes=30,
        reason="phase0",
        entry_kind="time_entry",
    )
    db.add(cr)
    db.commit()
    return cr


def test_admin_change_requests_list_excludes_tenant_b(
    _db_session, client_as_admin_a, admin_a, employee_b
):
    """GET /admin/change-requests — must not include Tenant B CRs."""
    cr_a = _make_pending_cr(_db_session, admin_a, TENANT_A_ID)
    cr_b = _make_pending_cr(_db_session, employee_b, TENANT_B_ID)

    resp = client_as_admin_a.get("/api/admin/change-requests")
    assert resp.status_code == 200, resp.text
    ids = {c["id"] for c in resp.json()}
    assert str(cr_a.id) in ids
    assert str(cr_b.id) not in ids


def test_admin_change_requests_pending_count_only_own_tenant(
    _db_session, client_as_admin_a, admin_a, employee_b
):
    """GET /admin/change-requests/pending-count — must count only Tenant A."""
    _make_pending_cr(_db_session, admin_a, TENANT_A_ID)
    _make_pending_cr(_db_session, employee_b, TENANT_B_ID)
    _make_pending_cr(_db_session, employee_b, TENANT_B_ID)

    resp = client_as_admin_a.get("/api/admin/change-requests/pending-count")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 1}


def _make_pending_vr(db, user, tenant_id, status_val="pending"):
    from app.models.vacation_request import VacationRequest

    vr = VacationRequest(
        id=uuid.uuid4(),
        user_id=user.id,
        tenant_id=tenant_id,
        date=date.today(),
        hours=8.0,
        absence_type="vacation",
        status=status_val,
    )
    db.add(vr)
    db.commit()
    return vr


def test_admin_vacation_requests_pending_count_only_own_tenant(
    _db_session, client_as_admin_a, admin_a, employee_b
):
    """GET /admin/vacation-requests/pending-count — counts only Tenant A pending VRs."""
    # Tenant A: one pending (counts) + one approved (must NOT count).
    _make_pending_vr(_db_session, admin_a, TENANT_A_ID)
    _make_pending_vr(_db_session, admin_a, TENANT_A_ID, status_val="approved")
    # Tenant B: two pending — must be excluded by the tenant filter.
    _make_pending_vr(_db_session, employee_b, TENANT_B_ID)
    _make_pending_vr(_db_session, employee_b, TENANT_B_ID)

    resp = client_as_admin_a.get("/api/admin/vacation-requests/pending-count")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 1}


def test_admin_change_requests_get_by_id_404_for_tenant_b(
    _db_session, client_as_admin_a, employee_b
):
    """GET /admin/change-requests/{id} — Tenant B CR must 404 for Tenant A admin."""
    cr_b = _make_pending_cr(_db_session, employee_b, TENANT_B_ID)

    resp = client_as_admin_a.get(f"/api/admin/change-requests/{cr_b.id}")
    assert resp.status_code == 404, resp.text


def test_admin_monthly_report_excludes_tenant_b_users(
    _db_session, client_as_admin_a, admin_a, employee_b
):
    """GET /admin/reports/monthly — must list only Tenant A users."""
    today = date.today()
    resp = client_as_admin_a.get(
        "/api/admin/reports/monthly",
        params={"month": f"{today.year}-{today.month:02d}"},
    )
    assert resp.status_code == 200, resp.text
    user_ids = {row["user_id"] for row in resp.json()}
    assert str(employee_b.id) not in user_ids


def test_holidays_list_excludes_tenant_b(_db_session, client_as_employee_a, two_tenants):
    """GET /api/holidays/?year=YYYY — must not return Tenant B's holidays."""
    from app.models.public_holiday import PublicHoliday
    year = date.today().year
    h_a = PublicHoliday(date=date(year, 1, 1), name="Tenant-A-Feiertag", year=year, tenant_id=TENANT_A_ID)
    h_b = PublicHoliday(date=date(year, 5, 1), name="Tenant-B-Feiertag", year=year, tenant_id=TENANT_B_ID)
    _db_session.add_all([h_a, h_b])
    _db_session.commit()

    resp = client_as_employee_a.get(f"/api/holidays/?year={year}")
    assert resp.status_code == 200, resp.text
    names = {h["name"] for h in resp.json()}
    assert "Tenant-A-Feiertag" in names
    assert "Tenant-B-Feiertag" not in names


def test_admin_a_bulk_approve_ignores_tenant_b_crs(_db_session, client_as_admin_a, employee_b):
    """Bulk approve: every item for Tenant B must be reported as failed, nothing mutated."""
    cr_b = ChangeRequest(
        id=uuid.uuid4(),
        user_id=employee_b.id,
        tenant_id=TENANT_B_ID,
        request_type=ChangeRequestType.CREATE,
        status=ChangeRequestStatus.PENDING,
        proposed_date=date.today(),
        proposed_start_time=time(9, 0),
        proposed_end_time=time(17, 0),
        proposed_break_minutes=30,
        reason="test",
        entry_kind="time_entry",
    )
    _db_session.add(cr_b)
    _db_session.commit()

    resp = client_as_admin_a.post(
        "/api/admin/change-requests/bulk-review",
        json={"request_ids": [str(cr_b.id)], "action": "approve"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["succeeded"] == 0
    assert body["failed"] == 1

    _db_session.expire_all()
    stored = _db_session.query(ChangeRequest).filter(ChangeRequest.id == cr_b.id).first()
    assert stored.status == ChangeRequestStatus.PENDING


# ─── Review 2026-05-29 (M-API1-4, M-DSG5): additional F-026 filter coverage ──


def _make_audit_log(db, user, tenant_id, action="create"):
    from app.models import TimeEntryAuditLog
    log = TimeEntryAuditLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user.id,
        changed_by=user.id,
        action=action,
        source="manual",
        new_note="cross-tenant-test",
    )
    db.add(log)
    db.commit()
    return log


def test_admin_audit_log_excludes_tenant_b(
    _db_session, client_as_admin_a, admin_a, employee_b
):
    """GET /admin/time-entries/audit-log — must not include Tenant B audit rows
    (admin_time_entries.list_audit_log had no explicit tenant filter)."""
    log_a = _make_audit_log(_db_session, admin_a, TENANT_A_ID)
    log_b = _make_audit_log(_db_session, employee_b, TENANT_B_ID)

    resp = client_as_admin_a.get("/api/admin/audit-log")
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert str(log_a.id) in ids
    assert str(log_b.id) not in ids


def test_admin_vacation_requests_list_excludes_tenant_b(
    _db_session, client_as_admin_a, admin_a, employee_b
):
    """GET /admin/vacation-requests — must not include Tenant B VRs
    (list_all_vacation_requests had no explicit tenant filter)."""
    vr_a = _make_pending_vr(_db_session, admin_a, TENANT_A_ID)
    vr_b = _make_pending_vr(_db_session, employee_b, TENANT_B_ID)

    resp = client_as_admin_a.get("/api/admin/vacation-requests")
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert str(vr_a.id) in ids
    assert str(vr_b.id) not in ids


def test_username_can_be_reused_across_tenants(
    _db_session, client_as_admin_a, employee_b
):
    """create_user uniqueness must be per-tenant: a username taken in Tenant B
    must still be creatable in Tenant A (usernames are unique per (tenant,name))."""
    # employee_b already exists in Tenant B with username "employee_b".
    resp = client_as_admin_a.post(
        "/api/admin/users",
        json={
            "username": "employee_b",
            "email": "fresh-a@test.local",
            "password": "Test2025!Password",
            "first_name": "Fresh",
            "last_name": "A",
            "role": "employee",
            "weekly_hours": 40.0,
            "vacation_days": 30,
            "work_days_per_week": 5,
        },
    )
    assert resp.status_code == 201, resp.text


def test_journal_holidays_exclude_tenant_b(_db_session, employee_a, two_tenants):
    """journal_service.get_journal must only see the user's own tenant holidays
    (PublicHoliday query had no tenant filter)."""
    from app.models.public_holiday import PublicHoliday
    from app.services import journal_service

    # June 2026: 1st = Monday (A holiday), 2nd = Tuesday (B holiday — must NOT leak).
    h_a = PublicHoliday(date=date(2026, 6, 1), name="A-Tag", year=2026, tenant_id=TENANT_A_ID)
    h_b = PublicHoliday(date=date(2026, 6, 2), name="B-Tag", year=2026, tenant_id=TENANT_B_ID)
    _db_session.add_all([h_a, h_b])
    _db_session.commit()

    result = journal_service.get_journal(_db_session, employee_a, 2026, 6)
    by_date = {d["date"]: d for d in result["days"]}
    assert by_date["2026-06-01"]["is_holiday"] is True   # own tenant holiday
    assert by_date["2026-06-02"]["is_holiday"] is False  # other tenant must not leak
