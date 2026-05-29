"""#156 / T2+T5: Tagesprinzip — ein freier Arbeitstag kostet GENAU 1 Urlaubstag,
unabhängig von Wochenstunden, Arbeitstagen/Woche und (wichtig!) der konkreten
Tagesverteilung. Insbesondere darf ein Montag-Urlaub nicht mehr kosten als ein
Dienstag-Urlaub (ungleichmäßiger Tagesplan)."""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User, UserRole
from app.services import calculation_service
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


def _client(db, user):
    def odb():
        yield db
    _APP.dependency_overrides[get_db] = odb
    _APP.dependency_overrides[get_current_user] = lambda: user
    return TestClient(_APP)


def _mk(db, **kw):
    base = dict(
        id=uuid.uuid4(), username=f"u{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.l",
        password_hash="x", first_name="A", last_name="B", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, work_days_per_week=5, vacation_days=30, track_hours=True,
        use_daily_schedule=False, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    base.update(kw)
    u = User(**base)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _book(db, u, d, hours=8):
    return _client(db, u).post("/api/absences", json={"date": d, "type": "vacation", "hours": hours})


def _used(db, u):
    return calculation_service.get_vacation_account(db, u, 2026)["used_days"]


MON, TUE = "2026-03-02", "2026-03-03"  # Mo / Di


def test_fulltime_one_day_is_one_day(db, default_tenant):
    u = _mk(db)  # 40h / 5 Tage
    assert _book(db, u, MON).status_code == 201
    assert _used(db, u) == 1.0


def test_uniform_parttime_one_day_is_one_day(db, default_tenant):
    u = _mk(db, weekly_hours=20.0, work_days_per_week=5)  # 4h/Tag
    assert _book(db, u, MON).status_code == 201
    assert _used(db, u) == 1.0


def test_three_day_week_one_day_is_one_day(db, default_tenant):
    u = _mk(db, weekly_hours=27.0, work_days_per_week=3, vacation_days=18)  # 9h/Tag
    assert _book(db, u, MON).status_code == 201
    assert _used(db, u) == 1.0


def test_uneven_schedule_monday_equals_tuesday(db, default_tenant):
    """Kernfall des Prüfers: Mo 8h, Di–Fr 3h. Ein Montag-Urlaub und ein
    Dienstag-Urlaub müssen beide GENAU 1,0 Tag kosten."""
    sched = dict(
        weekly_hours=20.0, work_days_per_week=5, use_daily_schedule=True,
        hours_monday=8, hours_tuesday=3, hours_wednesday=3, hours_thursday=3, hours_friday=3,
    )
    u_mon = _mk(db, **sched)
    assert _book(db, u_mon, MON).status_code == 201
    assert _used(db, u_mon) == 1.0  # darf NICHT 2,0 sein

    u_tue = _mk(db, **sched)
    assert _book(db, u_tue, TUE).status_code == 201
    assert _used(db, u_tue) == 1.0  # darf NICHT 0,75 sein


def test_full_week_equals_number_of_workdays(db, default_tenant):
    u = _mk(db, weekly_hours=20.0, work_days_per_week=5)  # 4h/Tag, 5 Tage
    r = _client(db, u).post(
        "/api/absences",
        json={"date": "2026-03-02", "end_date": "2026-03-06", "type": "vacation", "hours": 8},
    )
    assert r.status_code == 201, r.text
    assert _used(db, u) == 5.0
