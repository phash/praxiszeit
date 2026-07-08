"""#377 Minijob/MiLoG: Flag-Persistenz, 50-%-Prüfung, 12-Monats-FIFO-Aging.

Harness wie backend/tests/test_child_sick.py (lokale _app() + dependency_overrides,
/api-Pfade, headerloser TestClient).
"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, YearCarryover
from app.models.tenant import Tenant
from app.services import auth_service, milog_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

USERS = "/api/admin/users"


def _app() -> FastAPI:
    from app.routers import admin, time_entries, dashboard
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    a = FastAPI()
    limiter.enabled = False
    a.state.limiter = limiter
    a.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    a.include_router(admin.router)
    a.include_router(time_entries.router)
    a.include_router(dashboard.router)
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


def _user(db, username, role=UserRole.EMPLOYEE, weekly=Decimal("7.62")):
    u = User(username=username, email=f"{username}@x.de",
             password_hash=auth_service.hash_password("test123"),
             first_name=username, last_name="T", role=role, weekly_hours=weekly,
             vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "admin1", role=UserRole.ADMIN, weekly=Decimal("40"))


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


# --------------------------------------------------------------------------- #
# Flag persistence (create + update) — incl. the UserListResponse round-trip
# --------------------------------------------------------------------------- #
def test_milog_flag_persisted_on_create_and_update(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = client.post(USERS, json={
        "username": "mj", "first_name": "M", "last_name": "J", "password": "E2ePass1234!",
        "role": "employee", "weekly_hours": 7.62, "vacation_days": 30, "work_days_per_week": 5,
        "milog_working_time_account": True,
    }).json()["user"]["id"]
    assert client.get(f"{USERS}/{uid}").json()["milog_working_time_account"] is True
    client.put(f"{USERS}/{uid}", json={"milog_working_time_account": False})
    assert client.get(f"{USERS}/{uid}").json()["milog_working_time_account"] is False
    app.dependency_overrides.clear()


def test_userlist_carries_milog_and_childsick(db, admin, default_tenant):
    # Regression: das Edit-Formular liest die Liste; fehlen die Felder dort,
    # setzt jeder Save sie still auf Default (#376 + #377).
    client = _client_as(db, admin, admin)
    uid = client.post(USERS, json={
        "username": "mj2", "first_name": "M", "last_name": "J", "password": "E2ePass1234!",
        "role": "employee", "weekly_hours": 7.62, "vacation_days": 30, "work_days_per_week": 5,
        "milog_working_time_account": True, "child_sick_days_per_year": 12,
    }).json()["user"]["id"]
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert row["milog_working_time_account"] is True
    assert row["child_sick_days_per_year"] == 12
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# agreed_monthly_hours + 50% check (flat baseline)
# --------------------------------------------------------------------------- #
def test_agreed_monthly_hours_from_weekly(db, employee):
    employee.weekly_hours = Decimal("7.62")
    db.commit()
    got = milog_service.agreed_monthly_hours(db, employee, date(2026, 3, 1))
    assert Decimal("32.5") < got < Decimal("33.5")  # ≈ 33 h/Monat


def test_milog_50_check_flat_baseline(db, employee, monkeypatch):
    employee.weekly_hours = Decimal("7.62")
    employee.milog_working_time_account = False
    db.commit()
    # Ist = 55h → surplus 55−33 = 22h > cap 16,5h
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: Decimal("55"))
    # Flag aus → None
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None
    employee.milog_working_time_account = True
    db.commit()
    res = milog_service.milog_50_check(db, employee, 2026, 3)
    assert res is not None and res["account_hours"] > res["cap"]
    assert "Mindestlohnhöhe" in res["caveat"]
    # Ist = 40h → surplus 7h < cap → None
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: Decimal("40"))
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None
    # track_hours aus → None trotz hoher Ist
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: Decimal("99"))
    employee.track_hours = False
    db.commit()
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None


def test_flat_baseline_ignores_vacation_day(db, employee, monkeypatch):
    # Flache Basis: die 33h-Vertragsgröße hängt NICHT am (absenz-reduzierten)
    # Tages-Soll → ein Urlaubstag verschiebt cap/Basis nicht.
    employee.weekly_hours = Decimal("7.62"); employee.milog_working_time_account = True
    db.commit()
    # Die vereinbarte Monatszeit (Basis) = 33h, unabhängig vom (absenz-reduzierten)
    # Tages-Soll — ein Urlaubstag im Monat verschiebt sie nicht.
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: Decimal("50"))
    r = milog_service.milog_50_check(db, employee, 2026, 3)
    assert r["agreed_monthly"] == pytest.approx(33.0, abs=0.6)


# --------------------------------------------------------------------------- #
# settlement_aging FIFO + carryover seed + overdue semantics
# --------------------------------------------------------------------------- #
class _MO:
    def __init__(self, target, actual):
        self.target = Decimal(str(target))
        self.actual = Decimal(str(actual))
        self.cumulative = Decimal("0")


def test_settlement_aging_fifo_and_overdue(db, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    # +10h in 2025-01, −4h in 2025-06 (verbraucht Teil), Rest 6h altert
    hist = {(2025, 1): _MO(0, 10), (2025, 6): _MO(4, 0)}
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: hist)
    res = milog_service.settlement_aging(db, employee, date(2026, 3, 1))
    assert res["oldest_year"] == 2025 and res["oldest_month"] == 1
    assert abs(res["hours"] - 6.0) < 0.01
    assert res["age_months"] == 14 and res["overdue"] is True
    # Flag aus → None
    employee.milog_working_time_account = False
    db.commit()
    assert milog_service.settlement_aging(db, employee, date(2026, 3, 1)) is None


def test_settlement_aging_overdue_boundary(db, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    hist = {(2025, 3): _MO(0, 5)}
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: hist)
    # age 12 (2026-03) → NICHT überfällig, aber due_soon
    r12 = milog_service.settlement_aging(db, employee, date(2026, 3, 1))
    assert r12["age_months"] == 12 and r12["overdue"] is False and r12["due_soon"] is True
    # age 13 (2026-04) → überfällig
    r13 = milog_service.settlement_aging(db, employee, date(2026, 4, 1))
    assert r13["age_months"] == 13 and r13["overdue"] is True


def test_settlement_aging_seeds_carryover(db, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    # Jahresabschluss-Carryover 2025 = 8h offen; keine Monats-Deltas
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, year=2025,
                         overtime_hours=Decimal("8"), vacation_days=Decimal("0")))
    db.commit()
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: {(2025, 1): _MO(0, 0)})
    res = milog_service.settlement_aging(db, employee, date(2026, 6, 1))
    # geseedet auf Dez 2024 → sichtbar + überfällig
    assert res is not None and res["oldest_year"] == 2024 and res["oldest_month"] == 12
    assert abs(res["hours"] - 8.0) < 0.01 and res["overdue"] is True


# --------------------------------------------------------------------------- #
# Surfaces: users-overview (admin) · dashboard/overtime (MA) · create_time_entry
# --------------------------------------------------------------------------- #
def test_users_overview_milog_warnings(db, admin, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    monkeypatch.setattr("app.services.milog_service.settlement_aging", lambda *a, **k: None)
    client = _client_as(db, admin, admin)
    rows = client.get(f"{USERS}-overview").json()
    row = next(r for r in rows if r["user_id"] == str(employee.id))
    assert any("MILOG_ACCOUNT_50" in w for w in row["milog_warnings"])
    # Flag aus → leer
    employee.milog_working_time_account = False
    db.commit()
    rows2 = client.get(f"{USERS}-overview").json()
    assert next(r for r in rows2 if r["user_id"] == str(employee.id))["milog_warnings"] == []
    app.dependency_overrides.clear()


def test_dashboard_overtime_milog_warnings(db, admin, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    monkeypatch.setattr("app.services.milog_service.settlement_aging",
                        lambda *a, **k: {"oldest_year": 2025, "oldest_month": 1, "age_months": 18,
                                         "hours": 9.0, "overdue": True, "due_soon": False})
    client = _client_as(db, employee, admin)
    body = client.get("/api/dashboard/overtime").json()
    assert any("MILOG_ACCOUNT_50" in w for w in body["milog_warnings"])
    assert any("MILOG_SETTLEMENT_DUE" in w for w in body["milog_warnings"])
    app.dependency_overrides.clear()


def test_create_time_entry_emits_milog_for_flagged_user(db, admin, employee, monkeypatch):
    from app.services.timezone_service import today_local
    employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    client = _client_as(db, employee, admin)
    today = today_local().isoformat()
    r = client.post("/api/time-entries/", json={
        "date": today, "start_time": "09:00", "end_time": "12:00", "break_minutes": 0})
    assert r.status_code == 201, r.text
    assert any("MILOG_ACCOUNT_50" in w for w in r.json().get("warnings", []))
    app.dependency_overrides.clear()
