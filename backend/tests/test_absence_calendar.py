"""Calendar endpoint exposes per-employee colour for the badge ring (#157),
while DSGVO Art. 9 sick-masking stays intact."""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import Absence, AbsenceType, User, UserRole
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID


def _app() -> FastAPI:
    from app.routers import absences
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
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
    return TestClient(_APP)


def _mk_absence(db, user, d, typ):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=typ, hours=8.0)
    db.add(a)
    db.commit()
    return a


def _mk_employee(db, color):
    u = User(
        id=uuid.uuid4(), username=f"u_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@t.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Erika", last_name="Muster", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID, calendar_color=color,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_calendar_includes_user_color(db, test_user):
    _mk_absence(db, test_user, date(2026, 3, 2), AbsenceType.VACATION)
    resp = _client(db, test_user).get("/api/absences/calendar?month=2026-03")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["user_color"] == test_user.calendar_color
    assert rows[0]["type"] == "vacation"


def test_masked_sick_still_carries_user_color(db, test_user, default_tenant):
    # A different employee's SICK absence, viewed by a non-admin non-owner:
    # type is masked to "absent", but the ring colour must still be present.
    other = _mk_employee(db, "#AB12CD")
    _mk_absence(db, other, date(2026, 3, 4), AbsenceType.SICK)
    resp = _client(db, test_user).get("/api/absences/calendar?month=2026-03")
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["user_color"] == "#AB12CD")
    assert row["type"] == "absent"  # DSGVO masking intact
    assert row["user_color"] == "#AB12CD"
