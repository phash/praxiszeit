"""Teil B (Task 9): verkürzte Tage im öffentlichen /api/settings und die
Stempelkarten-Beschriftung ``today_special_day_label`` in /clock-status."""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import ReducedDay
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID, TestingSessionLocal

MONDAY = dt.date(2026, 2, 16)  # Rosenmontag
OTHER_TENANT = __import__("uuid").UUID("00000000-0000-0000-0000-0000000000aa")


def _app() -> FastAPI:
    from app.routers import time_entries as te_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="Reduced days public test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(te_router.router)
    return app


_APP = _app()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _APP.dependency_overrides.clear()


def _status(db, user, monkeypatch, today):
    import app.routers.time_entries as te

    monkeypatch.setattr(te, "_today_local", lambda: today)
    _APP.dependency_overrides[get_db] = lambda: db
    _APP.dependency_overrides[get_current_user] = lambda: user
    r = TestClient(_APP).get("/api/time-entries/clock-status")
    assert r.status_code == 200, r.text
    return r.json()


def _reduced(db, d=MONDAY, label="Rosenmontag", hours="4", tenant=DEFAULT_TENANT_ID):
    db.add(ReducedDay(tenant_id=tenant, date=d, label=label, max_hours=Decimal(hours)))
    db.commit()


def test_public_settings_does_not_list_reduced_days(db, test_user, monkeypatch):
    import app.main
    import app.database

    monkeypatch.setattr(app.main, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(app.database, "set_superadmin_context", lambda *_a, **_k: None)
    _reduced(db)
    db.add(SystemSetting(tenant_id=DEFAULT_TENANT_ID, key="special_day_dec24_mode", value="max_hours"))
    db.add(SystemSetting(tenant_id=DEFAULT_TENANT_ID, key="special_day_dec24_max_hours", value="4"))
    db.commit()

    body = app.main.get_public_settings()

    assert "reduced_days" not in body["special_days"]
    assert body["special_days"]["special_day_dec24_max_hours"] == 4.0
    assert set(body) <= {
        "vacation_approval_required", "break_exception_requires_approval",
        "special_days", "license",
    }


def _read_client(db, user):
    from app.routers import reduced_days

    app = FastAPI()
    app.include_router(reduced_days.read_router)
    app.dependency_overrides[get_db] = lambda: db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_read_endpoint_requires_auth(db, default_tenant):
    assert _read_client(db, None).get("/api/reduced-days").status_code in (401, 403)


def test_read_endpoint_tenant_filtered_sorted_and_year(db, test_user):
    from app.models.tenant import Tenant

    db.add(Tenant(id=OTHER_TENANT, name="Other", slug="other"))
    db.commit()
    _reduced(db, d=dt.date(2026, 3, 2), label="B", hours="2.5")
    _reduced(db, d=dt.date(2026, 2, 16), label="A")
    _reduced(db, d=dt.date(2027, 2, 8), label="C")
    _reduced(db, d=dt.date(2026, 2, 17), label="Fremd", tenant=OTHER_TENANT)
    c = _read_client(db, test_user)

    assert c.get("/api/reduced-days").json() == [
        {"date": "2026-02-16", "label": "A", "max_hours": 4.0},
        {"date": "2026-03-02", "label": "B", "max_hours": 2.5},
        {"date": "2027-02-08", "label": "C", "max_hours": 4.0},
    ]
    assert [r["label"] for r in c.get("/api/reduced-days?year=2026").json()] == ["A", "B"]


def test_clock_status_label_on_reduced_day(db, test_user, monkeypatch):
    _reduced(db)
    body = _status(db, test_user, monkeypatch, MONDAY)
    assert body["today_special_day_label"] == "verkürzter Tag (max. 4 h)"
    assert body["today_target_hours"] == 4.0


def test_clock_status_label_none_on_normal_day(db, test_user, monkeypatch):
    body = _status(db, test_user, monkeypatch, MONDAY)
    assert body["today_special_day_label"] is None


def test_clock_status_label_none_on_holiday(db, test_user, monkeypatch):
    _reduced(db)
    db.add(PublicHoliday(date=MONDAY, name="Feiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    body = _status(db, test_user, monkeypatch, MONDAY)
    assert body["today_special_day_label"] is None
    assert body["today_target_hours"] == 0.0


def test_clock_status_label_none_on_weekend(db, test_user, monkeypatch):
    sat = dt.date(2026, 2, 21)
    _reduced(db, d=sat)
    assert _status(db, test_user, monkeypatch, sat)["today_special_day_label"] is None


def test_clock_status_label_none_without_hour_tracking(db, test_user, monkeypatch):
    """F026: ohne Soll heute (Tag ohne Stundenzählung) keine Verkürzt-Beschriftung."""
    _reduced(db)
    test_user.track_hours = False
    db.commit()
    body = _status(db, test_user, monkeypatch, MONDAY)
    assert body["today_target_hours"] == 0.0
    assert body["today_special_day_label"] is None
