"""#156 Sofortmaßnahme: ein voller Abwesenheitstag wird immer mit dem
individuellen Tagessoll gebucht — nicht mit dem Formular-Default (8h).
Damit kostet ein freier Arbeitstag für Teilzeitkräfte genau 1,0 Urlaubstag."""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User, UserRole, Absence, AbsenceType
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


def _parttimer(db, weekly=20.0, days=5, overtime=False):
    u = User(
        id=uuid.uuid4(), username=f"pt{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.l",
        password_hash="x", first_name="Teil", last_name="Zeit", role=UserRole.EMPLOYEE,
        weekly_hours=weekly, work_days_per_week=days, vacation_days=30,
        track_hours=True, use_daily_schedule=False, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_single_day_vacation_stores_daily_target_not_8(db, default_tenant):
    # 20h / 5 days = 4h/day. Booking form sends the default 8h.
    u = _parttimer(db)
    resp = _client(db, u).post("/api/absences", json={
        "date": "2026-03-03", "type": "vacation", "hours": 8,  # client default
    })
    assert resp.status_code == 201, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["hours"] == 4.0  # the day's target, NOT the 8 we sent

    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["used_days"] == 1.0  # exactly one day for one free working day


def test_overtime_compensation_keeps_explicit_hours(db, default_tenant):
    # Überstundenausgleich darf die explizite Stundenzahl behalten (Teil-Abbau).
    u = _parttimer(db)
    resp = _client(db, u).post("/api/absences", json={
        "date": "2026-03-04", "type": "overtime", "hours": 2.5,
    })
    assert resp.status_code == 201, resp.text
    rows = resp.json()
    assert rows[0]["hours"] == 2.5  # overtime keeps the explicit amount
