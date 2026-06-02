"""Integration tests for #201 Arbeitszeit-Fenster: clock_in start clamping.

clock_in must cap an early start to [soll_start − grace] and preserve the raw
stamp in raw_start_time. Only the start side is tested here (end is open at
clock_in time).
"""

import datetime as dt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TimeEntry
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import (
    DEFAULT_TENANT_ID,
    engine,
    TestingSessionLocal,
)


# ---------------------------------------------------------------------------
# Test app
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    from app.routers import time_entries as te_router
    from app.routers import admin as admin_router

    app = FastAPI(title="PraxisZeit WorkWindow Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(te_router.router)
    app.include_router(admin_router.router)
    return app


_app = _create_test_app()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def default_tenant(db):
    tenant = Tenant(
        id=DEFAULT_TENANT_ID,
        name="Default",
        slug="default",
        is_active=True,
        mode="single",
    )
    db.add(tenant)
    db.commit()
    return tenant


@pytest.fixture(scope="function")
def employee(db, default_tenant):
    user = User(
        username="emp_ww",
        email="emp_ww@example.com",
        password_hash=auth_service.hash_password("test123"),
        first_name="Willi",
        last_name="Window",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        exempt_from_arbzg=False,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def admin(db, default_tenant):
    user = User(
        username="admin_ww",
        email="admin_ww@example.com",
        password_hash=auth_service.hash_password("admin123"),
        first_name="Admin",
        last_name="WorkWindow",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_client(db_session, current_user):
    def override_db():
        yield db_session

    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: current_user
    _app.dependency_overrides[require_admin] = lambda: current_user

    client = TestClient(_app)
    yield client

    _app.dependency_overrides.clear()


@pytest.fixture
def employee_client(db, employee):
    yield from _make_client(db, employee)


@pytest.fixture
def admin_client(db, admin):
    yield from _make_client(db, admin)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clock_in_caps_early_start(db, employee, employee_client, monkeypatch):
    """Stempelt ein MA 15 min vor Soll-Beginn (07:45 ist die Grenze bei grace=15,
    Soll 08:00), wird die gespeicherte start_time auf 07:45 gekappt.
    Der Rohstempel 07:00 landet in raw_start_time."""
    # Soll-Beginn Montag = 08:00; 2026-06-01 ist ein Montag.
    employee.scheduled_start_monday = dt.time(8, 0)
    db.commit()

    import app.routers.time_entries as te
    # Fix "now" to Monday 2026-06-01 07:00 — 60 min before soll_start.
    # Grace default = 15 min → floor = 07:45. The stamp (07:00) < floor → clamp.
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 7, 0))
    monkeypatch.setattr(te, "_today_local", lambda: dt.date(2026, 6, 1))

    resp = employee_client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code in (200, 201), resp.text

    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.start_time == dt.time(7, 45), f"Expected 07:45, got {entry.start_time}"
    assert entry.raw_start_time == dt.time(7, 0), f"Expected raw 07:00, got {entry.raw_start_time}"


def test_clock_in_early_start_warning(db, employee, employee_client, monkeypatch):
    """Frühstart-Kappung erzeugt EARLY_START-Warnung in der Response."""
    employee.scheduled_start_monday = dt.time(8, 0)
    db.commit()

    import app.routers.time_entries as te
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 7, 0))
    monkeypatch.setattr(te, "_today_local", lambda: dt.date(2026, 6, 1))

    resp = employee_client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code in (200, 201), resp.text

    warnings = resp.json().get("warnings", [])
    assert any(w.startswith("EARLY_START") for w in warnings), (
        f"Expected an EARLY_START warning, got: {warnings}"
    )


def test_clock_in_no_clamp_within_grace(db, employee, employee_client, monkeypatch):
    """Stempelt ein MA innerhalb des Puffers ein, bleibt start_time unverändert
    und raw_start_time ist NULL (keine Kappung)."""
    # Soll-Beginn Montag = 08:00; stamp at 07:50 (nur 10 min früh, grace=15 → kein Clamp).
    employee.scheduled_start_monday = dt.time(8, 0)
    db.commit()

    import app.routers.time_entries as te
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 7, 50))
    monkeypatch.setattr(te, "_today_local", lambda: dt.date(2026, 6, 1))

    resp = employee_client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code in (200, 201), resp.text

    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.start_time == dt.time(7, 50)
    assert entry.raw_start_time is None


def test_clock_in_no_window_configured(db, employee, employee_client, monkeypatch):
    """Ohne Soll-Zeiten (NULL) wird nicht gekappt — start_time = Rohstempel."""
    # scheduled_start_monday bleibt NULL (kein Soll-Fenster gesetzt).
    import app.routers.time_entries as te
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 6, 0))
    monkeypatch.setattr(te, "_today_local", lambda: dt.date(2026, 6, 1))

    resp = employee_client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code in (200, 201), resp.text

    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.start_time == dt.time(6, 0)
    assert entry.raw_start_time is None


def test_clock_out_caps_late_end(db, employee, employee_client, monkeypatch):
    import datetime as dt
    employee.scheduled_end_monday = dt.time(17, 0)
    db.commit()
    import app.routers.time_entries as te
    from app.models import TimeEntry
    db.add(TimeEntry(user_id=employee.id, tenant_id=employee.tenant_id,
                     date=dt.date(2026, 6, 1), start_time=dt.time(8, 0), end_time=None, break_minutes=0))
    db.commit()
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 18, 30))
    monkeypatch.setattr(te, "_today_local", lambda: dt.date(2026, 6, 1))
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 30})
    assert resp.status_code == 200, resp.text
    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.end_time == dt.time(17, 15)   # 17:00 + 15min grace
    assert entry.raw_end_time == dt.time(18, 30)


def test_manual_create_caps_both_ends(db, employee, employee_client, monkeypatch):
    """POST /api/time-entries klappt Start und Ende ins Soll-Fenster.

    Soll Mo 08:00–17:00, grace=15 min → floor=07:45, ceil=17:15.
    Eingabe: start=07:00 (< floor), end=18:00 (> ceil).
    Erwartet: start_time=07:45, raw_start_time=07:00,
               end_time=17:15, raw_end_time=18:00.
    Netto: (17:15 - 07:45) - 30min = 9h - 30min = 8,5h → < 10h (§3 ok).
    Monkeypatch _today_local → 2026-06-01 (Montag) damit employee (non-admin)
    Einträge für "heute" anlegen darf.
    """
    import datetime as dt
    import app.routers.time_entries as te

    employee.scheduled_start_monday = dt.time(8, 0)
    employee.scheduled_end_monday = dt.time(17, 0)
    db.commit()

    monkeypatch.setattr(te, "_today_local", lambda: dt.date(2026, 6, 1))

    resp = employee_client.post("/api/time-entries", json={
        "date": "2026-06-01",
        "start_time": "07:00",
        "end_time": "18:00",
        "break_minutes": 30,
    })
    assert resp.status_code == 201, resp.text

    from app.models import TimeEntry
    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.start_time == dt.time(7, 45), f"Expected 07:45, got {entry.start_time}"
    assert entry.raw_start_time == dt.time(7, 0), f"Expected raw_start 07:00, got {entry.raw_start_time}"
    assert entry.end_time == dt.time(17, 15), f"Expected 17:15, got {entry.end_time}"
    assert entry.raw_end_time == dt.time(18, 0), f"Expected raw_end 18:00, got {entry.raw_end_time}"


def test_admin_create_caps_both_ends(db, employee, admin, admin_client):
    """POST /api/admin/users/{id}/time-entries klappt Start und Ende des
    betroffenen Mitarbeiters ins Soll-Fenster.

    Soll Mo 08:00–17:00, grace=15 min → floor=07:45, ceil=17:15.
    Eingabe: start=07:00 (< floor), end=18:00 (> ceil), break=30.
    Erwartet: start_time=07:45, raw_start_time=07:00,
               end_time=17:15, raw_end_time=18:00.
    2026-06-01 ist ein Montag.
    """
    employee.scheduled_start_monday = dt.time(8, 0)
    employee.scheduled_end_monday = dt.time(17, 0)
    db.commit()

    resp = admin_client.post(
        f"/api/admin/users/{employee.id}/time-entries",
        json={
            "date": "2026-06-01",
            "start_time": "07:00",
            "end_time": "18:00",
            "break_minutes": 30,
        },
    )
    assert resp.status_code == 201, resp.text

    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.start_time == dt.time(7, 45), f"Expected 07:45, got {entry.start_time}"
    assert entry.raw_start_time == dt.time(7, 0), f"Expected raw_start 07:00, got {entry.raw_start_time}"
    assert entry.end_time == dt.time(17, 15), f"Expected 17:15, got {entry.end_time}"
    assert entry.raw_end_time == dt.time(18, 0), f"Expected raw_end 18:00, got {entry.raw_end_time}"


def test_cr_approval_create_clamps_to_soll_window(db, employee, admin, admin_client):
    """CR-Genehmigung (request_type=create, entry_kind=time_entry) klappt
    start_time ins Soll-Fenster und speichert den Rohwert in raw_start_time.

    Soll Mo 08:00 (scheduled_start_monday), grace=15 min → floor=07:45.
    CR proposed_start_time=07:00 (60 min zu früh) → nach Genehmigung:
      start_time=07:45, raw_start_time=07:00.
    2026-06-01 ist ein Montag.
    """
    from app.models.change_request import ChangeRequest, ChangeRequestType, ChangeRequestStatus

    # Soll-Beginn Montag 08:00; kein Soll-Ende → nur Start-Kappung.
    employee.scheduled_start_monday = dt.time(8, 0)
    db.commit()

    # CR direkt in der DB anlegen (pending, create, time_entry).
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID,
        user_id=employee.id,
        request_type=ChangeRequestType.CREATE,
        entry_kind="time_entry",
        status=ChangeRequestStatus.PENDING,
        proposed_date=dt.date(2026, 6, 1),
        proposed_start_time=dt.time(7, 0),
        proposed_end_time=dt.time(16, 0),
        proposed_break_minutes=30,
        reason="Frühschicht",
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)

    # Admin genehmigt den CR.
    resp = admin_client.post(
        f"/api/admin/change-requests/{cr.id}/review",
        json={"action": "approve"},
    )
    assert resp.status_code == 200, resp.text

    # Materialisierter TimeEntry muss gekappt sein.
    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.start_time == dt.time(7, 45), f"Expected 07:45 (clamped), got {entry.start_time}"
    assert entry.raw_start_time == dt.time(7, 0), f"Expected raw 07:00, got {entry.raw_start_time}"
    # Ende 16:00 liegt innerhalb des Fensters (kein Soll-Ende konfiguriert) → kein Clamp.
    assert entry.end_time == dt.time(16, 0), f"Expected 16:00 (unclamped), got {entry.end_time}"
    assert entry.raw_end_time is None, f"Expected raw_end_time=None, got {entry.raw_end_time}"
