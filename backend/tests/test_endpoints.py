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

def _create_endpoints_app() -> FastAPI:
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
        billing,
        superadmin,
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
    app.include_router(billing.router)
    app.include_router(billing.webhook_router)
    app.include_router(superadmin.router)

    # Health endpoint (duplicated from main.py since it is defined there directly)
    @app.get("/api/health")
    def health_check():
        return {"status": "healthy", "database": "connected"}

    return app


endpoints_app = _create_endpoints_app()

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

    endpoints_app.dependency_overrides[get_db] = _override_db
    endpoints_app.dependency_overrides[get_current_user] = _override_current_user

    with TestClient(endpoints_app) as client:
        yield client

    endpoints_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def admin_client(_db_session, admin_user):
    """TestClient authenticated as admin (get_current_user + require_admin overridden)."""

    def _override_db():
        yield _db_session

    def _override_current_user():
        return admin_user

    def _override_require_admin():
        return admin_user

    endpoints_app.dependency_overrides[get_db] = _override_db
    endpoints_app.dependency_overrides[get_current_user] = _override_current_user
    endpoints_app.dependency_overrides[require_admin] = _override_require_admin

    with TestClient(endpoints_app) as client:
        yield client

    endpoints_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def unauthenticated_client(_db_session):
    """TestClient without authentication overrides (no token)."""

    def _override_db():
        yield _db_session

    endpoints_app.dependency_overrides[get_db] = _override_db
    # Do NOT override get_current_user -- let the real dependency reject

    with TestClient(endpoints_app) as client:
        yield client

    endpoints_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """GET /api/health"""

    def test_health_returns_200(self, _db_session):
        """Prüft dass der Health-Endpoint 200 mit korrekter Struktur liefert — Basis-Monitoring."""
        def _override_db():
            yield _db_session

        endpoints_app.dependency_overrides[get_db] = _override_db

        with TestClient(endpoints_app) as client:
            resp = client.get("/api/health")

        endpoints_app.dependency_overrides.clear()

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

        endpoints_app.dependency_overrides[get_db] = _override_db

        # Patch set_superadmin_context because SQLite has no SET LOCAL
        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(endpoints_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "employee",
                    "password": "Employee2025!",
                })

        endpoints_app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "employee"

    def test_login_wrong_password(self, _db_session, employee_user):
        """Prüft dass falsches Passwort mit 401 abgelehnt wird — Brute-Force-Schutz."""
        def _override_db():
            yield _db_session

        endpoints_app.dependency_overrides[get_db] = _override_db

        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(endpoints_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "employee",
                    "password": "WrongPassword1!",
                })

        endpoints_app.dependency_overrides.clear()

        assert resp.status_code == 401
        assert "detail" in resp.json(), "401 without a detail message is a UX bug"

    def test_login_nonexistent_user(self, _db_session, tenant):
        """Prüft dass unbekannte Benutzernamen 401 liefern — Status-Code only
        genügt nicht für die Enumeration-Garantie; siehe
        ``test_login_nonexistent_vs_wrong_password_indistinguishable``."""
        def _override_db():
            yield _db_session

        endpoints_app.dependency_overrides[get_db] = _override_db

        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(endpoints_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "nobody",
                    "password": "SomePass1234!",
                })

        endpoints_app.dependency_overrides.clear()

        assert resp.status_code == 401

    def test_login_nonexistent_vs_wrong_password_indistinguishable(
        self, _db_session, employee_user,
    ):
        """Prüft dass existierender User + falsches Passwort UND
        nicht-existierender User IDENTISCHE Responses liefern — sonst kann
        ein Angreifer an der Antwort ablesen, ob ein Username existiert
        (Enumeration-Leak).

        Status-Code UND Body werden verglichen. Timing wird NICHT geprüft
        (F-040 setzt dafür einen Dummy-bcrypt-Hash, aber Timing-Unit-Tests
        sind zu flaky für diese Suite)."""
        def _override_db():
            yield _db_session

        endpoints_app.dependency_overrides[get_db] = _override_db

        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(endpoints_app) as client:
                existing = client.post("/api/auth/login", json={
                    "username": "employee",
                    "password": "DefinitelyWrong!1",
                })
                nonexistent = client.post("/api/auth/login", json={
                    "username": "no-such-user",
                    "password": "DefinitelyWrong!1",
                })

        endpoints_app.dependency_overrides.clear()

        assert existing.status_code == nonexistent.status_code == 401
        assert existing.json() == nonexistent.json(), (
            f"response bodies differ — enumeration leak: existing={existing.json()!r} "
            f"nonexistent={nonexistent.json()!r}"
        )

    def test_login_empty_body(self, _db_session, tenant):
        """Prüft dass leerer Login-Body 422 liefert — Pydantic-Validierung greift."""
        def _override_db():
            yield _db_session

        endpoints_app.dependency_overrides[get_db] = _override_db

        with TestClient(endpoints_app) as client:
            resp = client.post("/api/auth/login", json={})

        endpoints_app.dependency_overrides.clear()

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


class TestOnboardingComplete:
    """POST /api/auth/onboarding/complete — Erst-Login-Onboarding als gesehen markieren."""

    def test_complete_sets_timestamp(self, employee_client):
        """Markiert das Onboarding als gesehen; /me spiegelt den Zeitstempel."""
        resp = employee_client.post("/api/auth/onboarding/complete")
        assert resp.status_code == 200
        assert resp.json()["onboarding_completed_at"] is not None
        me = employee_client.get("/api/auth/me").json()
        assert me["onboarding_completed_at"] is not None

    def test_complete_is_idempotent(self, employee_client):
        """Mehrfaches Aufrufen aendert den ersten Zeitstempel nicht."""
        first = employee_client.post("/api/auth/onboarding/complete").json()["onboarding_completed_at"]
        second = employee_client.post("/api/auth/onboarding/complete").json()["onboarding_completed_at"]
        assert first is not None and second == first

    def test_complete_requires_auth(self, unauthenticated_client):
        """Ohne Token kein Zugriff."""
        resp = unauthenticated_client.post("/api/auth/onboarding/complete")
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
        """Prüft dass angelegte Zeiteintraege in der Liste erscheinen — Grundfunktion
        Zeiterfassung. ``==`` statt ``>=`` ist hier bewusst: wenn die Liste
        mehr als einen Eintrag enthält, ist entweder der Tenant-Filter kaputt
        oder Test-Isolation weg, beides wollen wir laut sehen."""
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
        assert len(data) == 1, f"expected exactly one entry, got {len(data)}: {data!r}"
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
        # 404 ohne detail wäre eine UX-Lücke — der Client kann nicht
        # unterscheiden zwischen "Eintrag weg" und "Endpoint kaputt".
        assert "detail" in resp.json()


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

        endpoints_app.dependency_overrides[get_db] = _override_db
        endpoints_app.dependency_overrides[get_current_user] = _override_current_user
        # Explicitly remove require_admin override if any leftover
        endpoints_app.dependency_overrides.pop(require_admin, None)

        with TestClient(endpoints_app) as client:
            resp = client.get("/api/admin/users")

        endpoints_app.dependency_overrides.clear()

        assert resp.status_code == 403
        body = resp.json()
        # Body must contain a detail message but MUST NOT leak the user's
        # role, email or any user-row data — defense-in-depth against
        # accidental enumeration via 403 responses.
        assert "detail" in body
        leak_terms = (
            employee_user.username,
            employee_user.email,
            "employee",  # role string
        )
        body_blob = str(body).lower()
        for term in leak_terms:
            assert term.lower() not in body_blob, f"403 leaks {term!r}: {body!r}"


class TestReceivesCompanyClosuresWiring:
    """#189: receives_company_closures flag round-trips through the admin API."""

    def test_create_user_persists_opt_out_flag(self, admin_client, _db_session):
        """POST with receives_company_closures=false persists it on the row."""
        resp = admin_client.post("/api/admin/users", json={
            "username": "verwaltung",
            "first_name": "Vera",
            "last_name": "Waltung",
            "weekly_hours": 40.0,
            "vacation_days": 30,
            "work_days_per_week": 5,
            "password": "VerwaltungPass2025!",
            "role": "admin",
            "receives_company_closures": False,
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["user"]["receives_company_closures"] is False
        created = _db_session.query(User).filter(User.username == "verwaltung").first()
        assert created.receives_company_closures is False

    def test_create_user_defaults_flag_true(self, admin_client):
        """Flag weggelassen -> True (jeder nimmt standardmäßig an Betriebsferien teil)."""
        resp = admin_client.post("/api/admin/users", json={
            "username": "normalo",
            "first_name": "Norm",
            "last_name": "Alo",
            "weekly_hours": 40.0,
            "vacation_days": 30,
            "work_days_per_week": 5,
            "password": "NormaloPass2025!",
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["user"]["receives_company_closures"] is True

    def test_update_user_toggles_flag(self, admin_client, employee_user, _db_session):
        """PUT kann das Flag umschalten (persistiert über exclude_unset/setattr)."""
        resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={
            "receives_company_closures": False,
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["receives_company_closures"] is False
        _db_session.refresh(employee_user)
        assert employee_user.receives_company_closures is False


class TestUsersOverview:
    """#194: GET /api/admin/users-overview — bulk vacation + YTD overtime per user."""

    def test_overview_returns_vacation_and_overtime_per_user(self, admin_client, admin_user, _db_session):
        from app.models import Absence, AbsenceType
        _db_session.add(Absence(
            user_id=admin_user.id, tenant_id=DEFAULT_TENANT_ID,
            date=date(2026, 3, 10), type=AbsenceType.VACATION, hours=8.0,
        ))
        _db_session.commit()

        resp = admin_client.get("/api/admin/users-overview", params={"year": 2026})
        assert resp.status_code == 200, resp.text
        row = next(r for r in resp.json() if r["user_id"] == str(admin_user.id))
        # vacation block carries the day figures the list renders
        assert row["vacation"]["used_days"] >= 1.0
        assert "remaining_days" in row["vacation"]
        # overtime block is the YTD summary
        assert row["overtime"]["year"] == 2026
        assert "overtime" in row["overtime"]

    def test_overview_excludes_inactive_by_default_includes_with_flag(self, admin_client, _db_session, tenant):
        inactive = User(
            username="inact", email="i@test.de",
            password_hash=auth_service.hash_password("Inactive2025!"),
            first_name="In", last_name="Active", role=UserRole.EMPLOYEE,
            weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
            is_active=False, tenant_id=DEFAULT_TENANT_ID,
        )
        _db_session.add(inactive)
        _db_session.commit()

        default_ids = [r["user_id"] for r in admin_client.get("/api/admin/users-overview").json()]
        assert str(inactive.id) not in default_ids

        incl_ids = [r["user_id"] for r in admin_client.get(
            "/api/admin/users-overview", params={"include_inactive": True}).json()]
        assert str(inactive.id) in incl_ids

    # Auth (employee -> 403) is structurally enforced by the router-level
    # dependencies=[Depends(require_admin)] and covered by
    # TestAdminUsers.test_employee_cannot_list_users — no separate test here.


class TestScheduledWindowRoundtrip:
    """#201: scheduled_start/end_monday..friday round-trip through admin user API."""

    def test_user_scheduled_window_roundtrip(self, admin_client, _db_session):
        resp = admin_client.post("/api/admin/users", json={
            "username": "win",
            "first_name": "Win",
            "last_name": "Dow",
            "weekly_hours": 40.0,
            "vacation_days": 30,
            "work_days_per_week": 5,
            "password": "WindowPass2025!",
            "scheduled_start_monday": "08:00",
            "scheduled_end_monday": "17:00",
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["user"]["scheduled_start_monday"] == "08:00:00"
        assert resp.json()["user"]["scheduled_end_monday"] == "17:00:00"
        assert resp.json()["user"]["scheduled_start_tuesday"] is None

        # Also verify the GET list includes the fields
        list_resp = admin_client.get("/api/admin/users")
        assert list_resp.status_code == 200
        users = list_resp.json()
        win = next((u for u in users if u["username"] == "win"), None)
        assert win is not None
        assert win["scheduled_start_monday"] == "08:00:00"
        assert win["scheduled_end_monday"] == "17:00:00"
        assert win["scheduled_start_tuesday"] is None

    def test_user_scheduled_window_update(self, admin_client, employee_user, _db_session):
        resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={
            "scheduled_start_friday": "09:00",
            "scheduled_end_friday": "15:00",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["scheduled_start_friday"] == "09:00:00"
        assert resp.json()["scheduled_end_friday"] == "15:00:00"


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
        assert "detail" in resp.json()

    def test_year_closing_invalid_year(self, admin_client):
        """Prüft dass ungueltige Jahreszahl 400 liefert — Input-Validierung."""
        resp = admin_client.post("/api/admin/year-closing/1999")
        assert resp.status_code == 400
        # Validation error must explain why the year is rejected, otherwise
        # a frontend can only show a generic "ungültig" message.
        body = resp.json()
        assert "detail" in body
        # The boundary (year ≥ 2000 or similar) should appear in the message
        # so the API doc and the client know why 1999 was rejected.
        assert any(c.isdigit() for c in str(body["detail"])), (
            f"400 detail for invalid year should mention a year/range: {body!r}"
        )

    def test_year_closing_as_employee_forbidden(self, _db_session, employee_user):
        """Prüft dass MA keinen Jahresabschluss ausloesen kann — nur Admin-Berechtigung."""
        def _override_db():
            yield _db_session

        def _override_current_user():
            return employee_user

        endpoints_app.dependency_overrides[get_db] = _override_db
        endpoints_app.dependency_overrides[get_current_user] = _override_current_user
        endpoints_app.dependency_overrides.pop(require_admin, None)

        with TestClient(endpoints_app) as client:
            resp = client.post("/api/admin/year-closing/2025")

        endpoints_app.dependency_overrides.clear()

        assert resp.status_code == 403
        assert "detail" in resp.json()


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
        body = resp.json()
        assert "detail" in body
        # Must not echo the requested ID back — that would let an attacker
        # confirm they're hitting the right endpoint with timing-stable
        # responses regardless of input.
        assert fake_id not in str(body["detail"])


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

    def test_clock_out_stale_entry_gets_closed(self, employee_client, _db_session, employee_user):
        """B-H1: ein offener Eintrag von einem früheren Tag wird beim Ausstempeln
        automatisch geschlossen UND committed (nicht durch das 400-Raise verworfen),
        sonst bliebe der Eintrag für immer offen."""
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        stale = TimeEntry(
            user_id=employee_user.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=yesterday,
            start_time=time(9, 0),
            end_time=None,  # open!
            break_minutes=0,
        )
        _db_session.add(stale)
        _db_session.commit()
        stale_id = stale.id

        resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0})
        assert resp.status_code == 400
        assert "früheren Tag" in resp.json()["detail"]

        # The stale entry must now be closed (auto-close committed), not open.
        _db_session.expire_all()
        closed = _db_session.query(TimeEntry).filter(TimeEntry.id == stale_id).one()
        assert closed.end_time is not None
        assert closed.end_time == time(23, 59)


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


class TestAdminSettings:
    """PUT /api/admin/settings/{key}"""

    def test_set_work_window_grace_minutes(self, admin_client):
        """#201: Gültige Pufferzeit wird gespeichert, negative Werte abgelehnt."""
        ok = admin_client.put("/api/admin/settings/work_window_grace_minutes", json={"value": "20"})
        assert ok.status_code == 200, ok.text
        bad = admin_client.put("/api/admin/settings/work_window_grace_minutes", json={"value": "-5"})
        assert bad.status_code == 400

    def test_inverted_scheduled_window_rejected(self, admin_client):
        """#201: Invertiertes Soll-Fenster (Start >= Ende) muss 422 liefern."""
        resp = admin_client.post("/api/admin/users", json={
            "username": "inv", "first_name": "In", "last_name": "V", "weekly_hours": 40.0,
            "vacation_days": 30, "work_days_per_week": 5, "password": "InvWindow2025!",
            "scheduled_start_monday": "18:00", "scheduled_end_monday": "08:00"})
        assert resp.status_code == 422, resp.text
