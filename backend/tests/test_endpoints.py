"""
TestClient-based endpoint tests for PraxisZeit backend.

Uses FastAPI's TestClient with dependency overrides for get_db,
get_current_user, and require_admin. Tests run against SQLite (not
PostgreSQL), so actual RLS cannot be tested -- focus is on HTTP-level
behavior: status codes, response shapes, and auth checks.
"""

import uuid
import pytest
from datetime import date, time, datetime, timezone
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

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
# Build a lightweight test app that includes all production routers but
# skips the production lifespan (which requires PostgreSQL, Prometheus, etc.)
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    """Create a FastAPI app identical to production but without lifespan."""
    from app.routers import (
        auth as auth_router,
        admin as admin_router,
        time_entries as te_router,
        absences,
        dashboard,
        holidays,
        reports,
        change_requests,
        company_closures,
        error_logs,
        vacation_requests,
        journal,
        import_xls,
        tenant_billing,
        public_signup,
    )

    app = FastAPI(title="PraxisZeit Test")

    # Rate limiter (required by login endpoint) — disabled for tests
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Register same routers as production
    app.include_router(auth_router.router)
    app.include_router(admin_router.router)
    app.include_router(te_router.router)
    app.include_router(absences.router)
    app.include_router(dashboard.router)
    app.include_router(holidays.router)
    app.include_router(reports.router)
    app.include_router(change_requests.router)
    app.include_router(company_closures.router)
    app.include_router(error_logs.router)
    app.include_router(vacation_requests.router)
    app.include_router(journal.router)
    app.include_router(import_xls.router)
    app.include_router(tenant_billing.router)
    app.include_router(public_signup.router)

    # Health endpoint (duplicated from main.py since it is defined there directly)
    @app.get("/api/health")
    def health_check():
        return {"status": "healthy", "database": "connected"}

    return app


test_app = _create_test_app()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def _db_session():
    """Provide a fresh SQLite database session per test."""
    # Drop first, then create -- ensures a clean slate even if a previous
    # test left partial state.  We disable FK checks during drop to avoid
    # ordering issues in SQLite.
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
def tenant(_db_session):
    """Create the default tenant."""
    t = Tenant(
        id=DEFAULT_TENANT_ID,
        name="Default",
        slug="default",
        is_active=True,
        mode="single",
    )
    _db_session.add(t)
    _db_session.commit()
    return t


@pytest.fixture(scope="function")
def employee_user(_db_session, tenant):
    """An employee user for tests."""
    user = User(
        username="employee",
        email="employee@test.de",
        password_hash=auth_service.hash_password("Employee2025!"),
        first_name="Max",
        last_name="Mustermann",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    _db_session.add(user)
    _db_session.commit()
    _db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def admin_user(_db_session, tenant):
    """An admin user for tests."""
    user = User(
        username="testadmin",
        email="admin@test.de",
        password_hash=auth_service.hash_password("AdminPass2025!"),
        first_name="Admin",
        last_name="Tester",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    _db_session.add(user)
    _db_session.commit()
    _db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def employee_client(_db_session, employee_user):
    """TestClient authenticated as employee (get_current_user overridden)."""

    def _override_db():
        yield _db_session

    def _override_current_user():
        return employee_user

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _override_current_user

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def admin_client(_db_session, admin_user):
    """TestClient authenticated as admin (get_current_user + require_admin overridden)."""

    def _override_db():
        yield _db_session

    def _override_current_user():
        return admin_user

    def _override_require_admin():
        return admin_user

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _override_current_user
    test_app.dependency_overrides[require_admin] = _override_require_admin

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def unauthenticated_client(_db_session):
    """TestClient without authentication overrides (no token)."""

    def _override_db():
        yield _db_session

    test_app.dependency_overrides[get_db] = _override_db
    # Do NOT override get_current_user -- let the real dependency reject

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """GET /api/health"""

    def test_health_returns_200(self, _db_session):
        """Prüft dass der Health-Endpoint 200 mit korrekter Struktur liefert — Basis-Monitoring."""
        def _override_db():
            yield _db_session

        test_app.dependency_overrides[get_db] = _override_db

        with TestClient(test_app) as client:
            resp = client.get("/api/health")

        test_app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


class TestAuthLogin:
    """POST /api/auth/login"""

    def test_login_valid_credentials(self, _db_session, employee_user):
        """Prüft dass gueltige Anmeldedaten ein JWT-Token liefern — Authentifizierungs-Kernfluss."""
        def _override_db():
            yield _db_session

        test_app.dependency_overrides[get_db] = _override_db

        # Patch set_superadmin_context because SQLite has no SET LOCAL
        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(test_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "employee",
                    "password": "Employee2025!",
                })

        test_app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "employee"

    def test_login_wrong_password(self, _db_session, employee_user):
        """Prüft dass falsches Passwort mit 401 abgelehnt wird — Brute-Force-Schutz."""
        def _override_db():
            yield _db_session

        test_app.dependency_overrides[get_db] = _override_db

        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(test_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "employee",
                    "password": "WrongPassword1!",
                })

        test_app.dependency_overrides.clear()

        assert resp.status_code == 401

    def test_login_nonexistent_user(self, _db_session, tenant):
        """Prüft dass unbekannte Benutzernamen 401 liefern — keine User-Enumeration."""
        def _override_db():
            yield _db_session

        test_app.dependency_overrides[get_db] = _override_db

        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(test_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "nobody",
                    "password": "SomePass1234!",
                })

        test_app.dependency_overrides.clear()

        assert resp.status_code == 401

    def test_login_empty_body(self, _db_session, tenant):
        """Prüft dass leerer Login-Body 422 liefert — Pydantic-Validierung greift."""
        def _override_db():
            yield _db_session

        test_app.dependency_overrides[get_db] = _override_db

        with TestClient(test_app) as client:
            resp = client.post("/api/auth/login", json={})

        test_app.dependency_overrides.clear()

        assert resp.status_code == 422


class TestAuthMe:
    """GET /api/auth/me"""

    def test_me_authenticated(self, employee_client):
        """Prüft dass authentifizierter User sein eigenes Profil abrufen kann."""
        resp = employee_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "employee"
        assert data["role"] == "employee"

    def test_me_unauthenticated(self, unauthenticated_client):
        """Prüft dass ohne Token kein Profilzugriff moeglich ist — DSGVO-Datenschutz."""
        resp = unauthenticated_client.get("/api/auth/me")
        assert resp.status_code in (401, 403)


class TestAuthLogout:
    """POST /api/auth/logout"""

    def test_logout_authenticated(self, employee_client):
        """Prüft dass Logout erfolgreich 200 liefert — Session-Beendigung."""
        resp = employee_client.post("/api/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data


# ---------------------------------------------------------------------------
# Time entry endpoints
# ---------------------------------------------------------------------------


class TestTimeEntryList:
    """GET /api/time-entries"""

    def test_list_empty(self, employee_client):
        """Prüft dass leere Zeiterfassungsliste 200 mit leerem Array liefert."""
        resp = employee_client.get("/api/time-entries/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_entry(self, _db_session, employee_user, employee_client):
        """Prüft dass angelegte Zeiteintraege in der Liste erscheinen — Grundfunktion Zeiterfassung."""
        entry = TimeEntry(
            user_id=employee_user.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=date.today(),
            start_time=time(8, 0),
            end_time=time(12, 0),
            break_minutes=0,
        )
        _db_session.add(entry)
        _db_session.commit()

        resp = employee_client.get("/api/time-entries/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["start_time"] == "08:00:00"


class TestTimeEntryCreate:
    """POST /api/time-entries"""

    def test_create_valid_entry(self, employee_client):
        """Prüft dass ein gueltiger Zeiteintrag mit 201 angelegt wird — Kernfunktion."""
        today = date.today().isoformat()
        resp = employee_client.post("/api/time-entries/", json={
            "date": today,
            "start_time": "08:00",
            "end_time": "12:00",
            "break_minutes": 0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["date"] == today
        assert data["start_time"] == "08:00:00"
        assert data["end_time"] == "12:00:00"

    def test_create_end_before_start(self, employee_client):
        """Prüft dass Ende vor Start abgelehnt wird — verhindert negative Arbeitszeiten."""
        today = date.today().isoformat()
        resp = employee_client.post("/api/time-entries/", json={
            "date": today,
            "start_time": "14:00",
            "end_time": "08:00",
            "break_minutes": 0,
        })
        assert resp.status_code == 422

    def test_create_missing_fields(self, employee_client):
        """Prüft dass fehlende Pflichtfelder 422 liefern — Input-Validierung."""
        resp = employee_client.post("/api/time-entries/", json={
            "date": date.today().isoformat(),
        })
        assert resp.status_code == 422


class TestTimeEntryDelete:
    """DELETE /api/time-entries/{entry_id}"""

    def test_delete_own_entry(self, _db_session, employee_user, employee_client):
        """Prüft dass MA eigene Eintraege loeschen kann — Korrekturrecht."""
        entry = TimeEntry(
            user_id=employee_user.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=date.today(),
            start_time=time(9, 0),
            end_time=time(11, 0),
            break_minutes=0,
        )
        _db_session.add(entry)
        _db_session.commit()
        _db_session.refresh(entry)

        resp = employee_client.delete(f"/api/time-entries/{entry.id}")
        assert resp.status_code == 204

    def test_delete_nonexistent_entry(self, employee_client):
        """Prüft dass Loeschen eines nicht existierenden Eintrags 404 liefert."""
        fake_id = str(uuid.uuid4())
        resp = employee_client.delete(f"/api/time-entries/{fake_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


class TestAdminUsers:
    """GET /api/admin/users"""

    def test_admin_list_users(self, admin_client, admin_user):
        """Prüft dass Admin alle Benutzer auflisten kann — Verwaltungsfunktion."""
        resp = admin_client.get("/api/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # At least the admin user itself should be present
        usernames = [u["username"] for u in data]
        assert "testadmin" in usernames

    def test_employee_cannot_list_users(self, _db_session, employee_user):
        """Prüft dass MA keinen Zugriff auf Admin-Endpunkte hat — Rollenbasierte Autorisierung."""
        def _override_db():
            yield _db_session

        # Override get_current_user to return the employee, but do NOT
        # override require_admin -- let it enforce the admin check.
        def _override_current_user():
            return employee_user

        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = _override_current_user
        # Explicitly remove require_admin override if any leftover
        test_app.dependency_overrides.pop(require_admin, None)

        with TestClient(test_app) as client:
            resp = client.get("/api/admin/users")

        test_app.dependency_overrides.clear()

        assert resp.status_code == 403


class TestAdminYearClosing:
    """POST / DELETE /api/admin/year-closing/{year}"""

    def test_create_year_closing(self, _db_session, admin_user, admin_client):
        """Prüft dass Jahresabschluss 200 mit Carryover-Daten liefert — Jahreswechsel-Workflow."""
        # The admin_user has track_hours=True by default, so they will be
        # included. The service calculates carryovers. This just checks the
        # HTTP-level behavior.
        resp = admin_client.post("/api/admin/year-closing/2025")
        assert resp.status_code == 200
        data = resp.json()
        assert data["year"] == 2025
        assert data["next_year"] == 2026
        assert "employees" in data

    def test_delete_year_closing_no_data(self, admin_client):
        """Prüft dass Loeschen ohne vorhandene Carryover-Daten 404 liefert."""
        resp = admin_client.delete("/api/admin/year-closing/2024")
        assert resp.status_code == 404

    def test_year_closing_invalid_year(self, admin_client):
        """Prüft dass ungueltige Jahreszahl 400 liefert — Input-Validierung."""
        resp = admin_client.post("/api/admin/year-closing/1999")
        assert resp.status_code == 400

    def test_year_closing_as_employee_forbidden(self, _db_session, employee_user):
        """Prüft dass MA keinen Jahresabschluss ausloesen kann — nur Admin-Berechtigung."""
        def _override_db():
            yield _db_session

        def _override_current_user():
            return employee_user

        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = _override_current_user
        test_app.dependency_overrides.pop(require_admin, None)

        with TestClient(test_app) as client:
            resp = client.post("/api/admin/year-closing/2025")

        test_app.dependency_overrides.clear()

        assert resp.status_code == 403


class TestAdminCarryovers:
    """GET /api/admin/users/{user_id}/carryovers"""

    def test_list_carryovers_empty(self, admin_client, employee_user):
        """Prüft dass Carryover-Liste ohne Daten 200 mit leerem Array liefert."""
        resp = admin_client.get(f"/api/admin/users/{employee_user.id}/carryovers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_carryovers_unknown_user(self, admin_client):
        """Prüft dass Carryover-Abfrage fuer unbekannten User 404 liefert."""
        fake_id = str(uuid.uuid4())
        resp = admin_client.get(f"/api/admin/users/{fake_id}/carryovers")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Clock-in / Clock-out
# ---------------------------------------------------------------------------


class TestClockEndpoints:
    """POST /api/time-entries/clock-in, /clock-out, GET /clock-status"""

    def test_clock_status_not_clocked_in(self, employee_client):
        """Prüft dass Stempel-Status 'nicht eingestempelt' korrekt gemeldet wird."""
        resp = employee_client.get("/api/time-entries/clock-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_clocked_in"] is False

    def test_clock_in(self, employee_client):
        """Prüft dass Einstempeln einen offenen Eintrag ohne Endzeit erstellt."""
        resp = employee_client.post("/api/time-entries/clock-in", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert data["end_time"] is None
        assert data["date"] == date.today().isoformat()

    def test_clock_in_twice_fails(self, employee_client):
        """Prüft dass doppeltes Einstempeln verhindert wird — keine Doppeleintraege."""
        employee_client.post("/api/time-entries/clock-in", json={})
        resp = employee_client.post("/api/time-entries/clock-in", json={})
        assert resp.status_code == 400

    def test_clock_out_without_clock_in(self, employee_client):
        """Prüft dass Ausstempeln ohne Einstempeln abgelehnt wird — konsistenter Zustand."""
        resp = employee_client.post("/api/time-entries/clock-out", json={
            "break_minutes": 0,
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Auth: change password
# ---------------------------------------------------------------------------


class TestChangePassword:
    """POST /api/auth/change-password"""

    def test_change_password_wrong_current(self, employee_client):
        """Prüft dass falsches aktuelles Passwort die Aenderung verhindert — Sicherheit."""
        resp = employee_client.post("/api/auth/change-password", json={
            "current_password": "WrongOldPassword1!",
            "new_password": "NewSecure2025!",
        })
        assert resp.status_code == 400

    def test_change_password_success(self, employee_client):
        """Prüft dass Passwortwechsel mit korrektem altem Passwort neues Token liefert."""
        resp = employee_client.post("/api/auth/change-password", json={
            "current_password": "Employee2025!",
            "new_password": "NewSecure2025!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    def test_change_password_weak_new(self, employee_client):
        """Prüft dass zu schwaches neues Passwort 422 liefert — Passwort-Policy."""
        resp = employee_client.post("/api/auth/change-password", json={
            "current_password": "Employee2025!",
            "new_password": "short",
        })
        assert resp.status_code == 422
