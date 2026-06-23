"""Regression tests for #284 — phantom 'Gelöscht' entries in the per-employee
Änderungsprotokoll.

Opening an employee in the admin dashboard issues GET /api/absences?user_id=X,
which writes a DSGVO access-log row (action 'absence_list_read' / 'health_data_read',
#208). The per-employee change-log view then fetched ALL audit rows for that user
and the frontend rendered every non-create/update action as 'Gelöscht' — so each
open produced a fresh phantom deletion.

The operational change-log view must request only real change actions
(create/update/delete). The dedicated compliance audit page keeps full visibility.
"""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, User, UserRole
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID


def _app() -> FastAPI:
    from app.routers import absences, admin_time_entries
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    app.include_router(admin_time_entries.router)
    return app


_APP = _app()


@pytest.fixture(autouse=True)
def _clear():
    yield
    _APP.dependency_overrides.clear()


def _client(db, current):
    def odb():
        yield db
    _APP.dependency_overrides[get_db] = odb
    _APP.dependency_overrides[get_current_user] = lambda: current
    _APP.dependency_overrides[require_admin] = lambda: current
    return TestClient(_APP)


def _mk_employee(db) -> User:
    u = User(
        id=uuid.uuid4(), username=f"u_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@t.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Erika", last_name="Muster", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _open_employee_absences(db, admin, employee):
    """Simulate the dashboard opening an employee → writes the DSGVO read-log row."""
    resp = _client(db, admin).get(f"/api/absences?user_id={employee.id}")
    assert resp.status_code == 200, resp.text


def test_changes_only_excludes_dsgvo_read_access_rows(db, test_admin):
    employee = _mk_employee(db)
    # Admin opens the employee twice → two DSGVO access-log rows are written.
    _open_employee_absences(db, test_admin, employee)
    _open_employee_absences(db, test_admin, employee)

    resp = _client(db, test_admin).get(
        f"/api/admin/audit-log?user_id={employee.id}&changes_only=true"
    )
    assert resp.status_code == 200, resp.text
    actions = [row["action"] for row in resp.json()]
    # The reported bug: read-access rows leaked into the change log and were
    # rendered as 'Gelöscht'. They must NOT appear in the changes-only view.
    assert "absence_list_read" not in actions
    assert "health_data_read" not in actions
    assert all(a in ("create", "update", "delete") for a in actions), actions


def test_full_audit_log_still_includes_access_rows_for_compliance(db, test_admin):
    employee = _mk_employee(db)
    _open_employee_absences(db, test_admin, employee)

    # The dedicated compliance page (no changes_only filter) keeps full visibility
    # of access events — DSGVO Art. 5(2) accountability must not be hidden.
    resp = _client(db, test_admin).get(f"/api/admin/audit-log?user_id={employee.id}")
    assert resp.status_code == 200, resp.text
    actions = [row["action"] for row in resp.json()]
    assert "absence_list_read" in actions
