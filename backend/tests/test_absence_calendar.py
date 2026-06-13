"""Calendar endpoint exposes per-employee colour for the badge ring (#157),
while DSGVO Art. 9 sick-masking stays intact."""
import uuid
from datetime import date, timedelta

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


def test_masking_indistinguishable_from_other_sensitive_types(db, test_user, default_tenant):
    """DSGVO Art. 9: the masked bucket must NOT be a 1:1 tell for sick-leave.

    If only SICK were rewritten to "absent" while every other type kept its
    real value, a colleague could deterministically infer health status from
    the unique "absent" bucket. OTHER and PAID_LEAVE (potentially sensitive /
    unspecified) must therefore also collapse to "absent" for non-admin
    viewers of *other* employees — so "absent" means sick-or-other-or-paidleave,
    not sick. Non-sensitive planning types (VACATION) stay truthful.
    """
    other = _mk_employee(db, "#FE01DC")
    _mk_absence(db, other, date(2026, 3, 10), AbsenceType.OTHER)
    _mk_absence(db, other, date(2026, 3, 11), AbsenceType.PAID_LEAVE)
    _mk_absence(db, other, date(2026, 3, 12), AbsenceType.VACATION)
    resp = _client(db, test_user).get("/api/absences/calendar?month=2026-03")
    assert resp.status_code == 200, resp.text
    by_date = {r["date"]: r["type"] for r in resp.json() if r["user_color"] == "#FE01DC"}
    assert by_date["2026-03-10"] == "absent", "OTHER must be masked so 'absent' isn't unique to sick"
    assert by_date["2026-03-11"] == "absent", "PAID_LEAVE must be masked too"
    assert by_date["2026-03-12"] == "vacation", "VACATION stays truthful (non-sensitive planning info)"


def test_team_upcoming_masks_all_sensitive_types(db, test_user, default_tenant):
    """DSGVO Art. 9: /team/upcoming must mask the SAME sensitive set as /calendar.

    Regression for the leak where /team/upcoming masked only SICK while OTHER /
    PAID_LEAVE kept their real value — making the "absent" bucket a 1:1 tell for
    sick-leave on the colleague-facing upcoming feed. VACATION stays truthful.
    """
    from app.services.timezone_service import today_local
    base = today_local() + timedelta(days=14)
    other = _mk_employee(db, "#C0FFEE")
    _mk_absence(db, other, base, AbsenceType.SICK)
    _mk_absence(db, other, base + timedelta(days=1), AbsenceType.OTHER)
    _mk_absence(db, other, base + timedelta(days=2), AbsenceType.PAID_LEAVE)
    _mk_absence(db, other, base + timedelta(days=3), AbsenceType.VACATION)

    resp = _client(db, test_user).get("/api/absences/team/upcoming")
    assert resp.status_code == 200, resp.text
    by_date = {r["date"]: r["type"] for r in resp.json() if r["user_color"] == "#C0FFEE"}
    assert by_date[str(base)] == "absent", "SICK masked"
    assert by_date[str(base + timedelta(days=1))] == "absent", "OTHER must be masked too"
    assert by_date[str(base + timedelta(days=2))] == "absent", "PAID_LEAVE must be masked too"
    assert by_date[str(base + timedelta(days=3))] == "vacation", "VACATION stays truthful"


def test_own_sensitive_absence_not_masked_to_self(db, test_user):
    """The owner still sees their own real absence type (masking is for *others*)."""
    _mk_absence(db, test_user, date(2026, 3, 13), AbsenceType.OTHER)
    resp = _client(db, test_user).get("/api/absences/calendar?month=2026-03")
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["date"] == "2026-03-13")
    assert row["type"] == "other"


def test_calendar_department_visible_to_admin(db, test_user, test_admin):
    """#162 + DSGVO: admins see the department (for the filter)."""
    test_user.department = "Verwaltung"
    db.commit()
    _mk_absence(db, test_user, date(2026, 3, 6), AbsenceType.VACATION)
    resp = _client(db, test_admin).get("/api/absences/calendar?month=2026-03")
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["user_color"] == test_user.calendar_color)
    assert row["department"] == "Verwaltung"


def test_calendar_department_hidden_from_non_admin(db, test_user):
    """DSGVO-Minimierung: Kolleg:innen erhalten die Abteilung NICHT broadcastet."""
    test_user.department = "Verwaltung"
    db.commit()
    _mk_absence(db, test_user, date(2026, 3, 7), AbsenceType.VACATION)
    resp = _client(db, test_user).get("/api/absences/calendar?month=2026-03")
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["user_color"] == test_user.calendar_color)
    assert row["department"] is None
