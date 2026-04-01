"""Tests for absence request approval flow (GitHub Issue #75).

Verifies that approved absence requests (Anträge) of any type
create the correct absence entries in the journal, including:
- Fall 1: No existing entry → creates absence
- Fall 2: Existing TimeEntry → deletes it, creates absence
- Fall 3: Rejected request → no changes
"""

import uuid
import pytest
from datetime import date, time, datetime, timezone
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TimeEntry, Absence, AbsenceType, TimeEntryAuditLog
from app.models.tenant import Tenant
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from tests.conftest import (
    DEFAULT_TENANT_ID,
    engine,
    TestingSessionLocal,
)


# ---------------------------------------------------------------------------
# Test app setup
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    from app.routers import (
        admin_vacations,
        vacation_requests,
        absences,
        journal,
    )

    app = FastAPI(title="PraxisZeit Absence Request Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(admin_vacations.router)
    app.include_router(vacation_requests.router)
    app.include_router(absences.router)
    app.include_router(journal.router)

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
    from app.services import auth_service
    user = User(
        username="employee1",
        email="emp@example.com",
        password_hash=auth_service.hash_password("test123"),
        first_name="Anna",
        last_name="Müller",
        role=UserRole.EMPLOYEE,
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


@pytest.fixture(scope="function")
def admin(db, default_tenant):
    from app.services import auth_service
    user = User(
        username="admin1",
        email="admin@example.com",
        password_hash=auth_service.hash_password("admin123"),
        first_name="Chef",
        last_name="Admin",
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
    """Create a TestClient with overridden dependencies."""
    def override_db():
        try:
            yield db_session
        finally:
            pass

    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: current_user
    _app.dependency_overrides[require_admin] = lambda: current_user

    client = TestClient(_app)
    yield client

    _app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db, admin):
    yield from _make_client(db, admin)


@pytest.fixture
def employee_client(db, employee):
    yield from _make_client(db, employee)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _create_pending_request(db, employee, absence_type="training",
                            req_date=date(2025, 3, 12), hours=8.0, note=None):
    """Insert a pending VacationRequest directly into DB."""
    vr = VacationRequest(
        user_id=employee.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=req_date,
        hours=hours,
        absence_type=absence_type,
        note=note or f"Test {absence_type}",
        status=VacationRequestStatus.PENDING.value,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


# ---------------------------------------------------------------------------
# Tests: Fall 1 — No existing entry, approve → creates absence
# ---------------------------------------------------------------------------

class TestFall1_ApproveCreatesAbsence:
    """Fall 1: User hat keinen Zeiteintrag → Antrag genehmigt → Abwesenheit erstellt."""

    def test_approve_training_creates_training_absence(self, db, employee, admin_client):
        """Fortbildung-Antrag genehmigt → Absence(type=TRAINING) angelegt."""
        vr = _create_pending_request(db, employee, absence_type="training",
                                      req_date=date(2025, 3, 12))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"

        # Check absence was created
        absence = db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 12),
        ).first()
        assert absence is not None
        assert absence.type == AbsenceType.TRAINING
        assert float(absence.hours) == 8.0

    def test_approve_vacation_creates_vacation_absence(self, db, employee, admin_client):
        """Urlaubsantrag genehmigt → Absence(type=VACATION) angelegt."""
        vr = _create_pending_request(db, employee, absence_type="vacation",
                                      req_date=date(2025, 3, 12))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 200

        absence = db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 12),
        ).first()
        assert absence is not None
        assert absence.type == AbsenceType.VACATION

    def test_approve_overtime_creates_overtime_absence(self, db, employee, admin_client):
        """Überstundenausgleich-Antrag → Absence(type=OVERTIME)."""
        vr = _create_pending_request(db, employee, absence_type="overtime",
                                      req_date=date(2025, 3, 12))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 200

        absence = db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 12),
        ).first()
        assert absence is not None
        assert absence.type == AbsenceType.OVERTIME

    def test_response_includes_absence_type(self, db, employee, admin_client):
        """Response enthält absence_type."""
        vr = _create_pending_request(db, employee, absence_type="training")
        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 200
        assert resp.json()["absence_type"] == "training"


# ---------------------------------------------------------------------------
# Tests: Fall 2 — Existing TimeEntry, approve → overwrites with absence
# ---------------------------------------------------------------------------

class TestFall2_ApproveOverwritesTimeEntry:
    """Fall 2: Bestehender Zeiteintrag → Antrag genehmigt → Eintrag ersetzt."""

    def test_existing_time_entry_deleted_on_approve(self, db, employee, admin_client):
        """Bestehender TimeEntry wird beim Genehmigen gelöscht."""
        # Create existing time entry on the date
        entry = TimeEntry(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=date(2025, 3, 11),
            start_time=time(8, 0),
            end_time=time(16, 0),
            break_minutes=30,
        )
        db.add(entry)
        db.commit()

        # Verify entry exists
        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id,
            TimeEntry.date == date(2025, 3, 11),
        ).count() == 1

        # Create and approve training request for same date
        vr = _create_pending_request(db, employee, absence_type="training",
                                      req_date=date(2025, 3, 11))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 200

        # TimeEntry should be deleted
        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id,
            TimeEntry.date == date(2025, 3, 11),
        ).count() == 0

        # Absence should be created
        absence = db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 11),
        ).first()
        assert absence is not None
        assert absence.type == AbsenceType.TRAINING

    def test_multiple_time_entries_deleted_on_approve(self, db, employee, admin_client):
        """Mehrere TimeEntries am selben Tag werden alle gelöscht."""
        for start_h, end_h in [(8, 12), (13, 17)]:
            entry = TimeEntry(
                user_id=employee.id,
                tenant_id=DEFAULT_TENANT_ID,
                date=date(2025, 3, 11),
                start_time=time(start_h, 0),
                end_time=time(end_h, 0),
                break_minutes=0,
            )
            db.add(entry)
        db.commit()

        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id,
            TimeEntry.date == date(2025, 3, 11),
        ).count() == 2

        vr = _create_pending_request(db, employee, absence_type="training",
                                      req_date=date(2025, 3, 11))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 200

        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id,
            TimeEntry.date == date(2025, 3, 11),
        ).count() == 0

    def test_deleted_time_entry_has_audit_log(self, db, employee, admin, admin_client):
        """Gelöschte TimeEntries erzeugen Audit-Log-Einträge."""
        entry = TimeEntry(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=date(2025, 3, 11),
            start_time=time(8, 0),
            end_time=time(16, 0),
            break_minutes=30,
        )
        db.add(entry)
        db.commit()
        entry_id = entry.id

        vr = _create_pending_request(db, employee, absence_type="training",
                                      req_date=date(2025, 3, 11))
        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 200

        # Check audit log was created
        audit = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.time_entry_id == entry_id,
            TimeEntryAuditLog.action == "delete",
        ).first()
        assert audit is not None
        assert audit.source == "absence_request_approval"
        assert audit.changed_by == admin.id


# ---------------------------------------------------------------------------
# Tests: Fall 3 — Reject → no changes
# ---------------------------------------------------------------------------

class TestFall3_RejectNoChanges:
    """Fall 3: Antrag abgelehnt → keine Änderungen."""

    def test_reject_creates_no_absence(self, db, employee, admin_client):
        """Abgelehnter Antrag erstellt keine Abwesenheit."""
        vr = _create_pending_request(db, employee, absence_type="training",
                                      req_date=date(2025, 3, 10))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "reject", "rejection_reason": "Kein Bedarf"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        absence = db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 10),
        ).first()
        assert absence is None

    def test_reject_preserves_existing_time_entry(self, db, employee, admin_client):
        """Ablehnung lässt bestehende Zeiteinträge unverändert."""
        entry = TimeEntry(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=date(2025, 3, 10),
            start_time=time(8, 0),
            end_time=time(16, 0),
            break_minutes=30,
        )
        db.add(entry)
        db.commit()

        vr = _create_pending_request(db, employee, absence_type="training",
                                      req_date=date(2025, 3, 10))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "reject"},
        )
        assert resp.status_code == 200

        # TimeEntry still exists
        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id,
            TimeEntry.date == date(2025, 3, 10),
        ).count() == 1


# ---------------------------------------------------------------------------
# Tests: Schema validation
# ---------------------------------------------------------------------------

class TestAbsenceTypeValidation:
    """Validate absence_type field in request creation."""

    def test_create_request_with_training_type(self, db, employee, employee_client):
        """Employee kann Antrag mit absence_type=training erstellen."""
        # Enable approval required setting
        from app.models.system_setting import SystemSetting
        setting = SystemSetting(
            key="vacation_approval_required",
            value="true",
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(setting)
        db.commit()

        resp = employee_client.post("/api/vacation-requests/", json={
            "date": "2025-03-12",
            "hours": 8.0,
            "absence_type": "training",
            "note": "Fortbildung XYZ",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["absence_type"] == "training"

    def test_create_request_defaults_to_vacation(self, db, employee, employee_client):
        """Ohne absence_type → default 'vacation'."""
        from app.models.system_setting import SystemSetting
        setting = SystemSetting(
            key="vacation_approval_required",
            value="true",
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(setting)
        db.commit()

        resp = employee_client.post("/api/vacation-requests/", json={
            "date": "2025-03-12",
            "hours": 8.0,
        })
        assert resp.status_code == 201
        assert resp.json()["absence_type"] == "vacation"

    def test_create_request_rejects_sick_type(self, db, employee, employee_client):
        """absence_type=sick wird abgelehnt (Krankmeldung braucht keinen Antrag)."""
        from app.models.system_setting import SystemSetting
        setting = SystemSetting(
            key="vacation_approval_required",
            value="true",
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(setting)
        db.commit()

        resp = employee_client.post("/api/vacation-requests/", json={
            "date": "2025-03-12",
            "hours": 8.0,
            "absence_type": "sick",
        })
        assert resp.status_code == 422  # Validation error


# ---------------------------------------------------------------------------
# Tests: Vacation budget check only for vacation type
# ---------------------------------------------------------------------------

class TestVacationBudgetCheck:
    """Vacation budget nur bei type=vacation geprüft."""

    def test_training_skips_vacation_budget_check(self, db, employee, admin_client):
        """Training-Antrag prüft kein Urlaubsguthaben."""
        # Set vacation_days to 0 so budget is exhausted
        employee.vacation_days = 0
        db.commit()

        vr = _create_pending_request(db, employee, absence_type="training",
                                      req_date=date(2025, 3, 12))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        # Should succeed — training doesn't check vacation budget
        assert resp.status_code == 200

    def test_vacation_checks_budget(self, db, employee, admin_client):
        """Urlaubs-Antrag prüft Urlaubsguthaben."""
        employee.vacation_days = 0
        db.commit()

        vr = _create_pending_request(db, employee, absence_type="vacation",
                                      req_date=date(2025, 3, 12))

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 400
        assert "Urlaubstage" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: Admin list endpoint shows absence_type
# ---------------------------------------------------------------------------

class TestAdminListEndpoint:
    """Admin-Endpunkt zeigt absence_type."""

    def test_list_shows_absence_type(self, db, employee, admin_client):
        """GET /admin/vacation-requests enthält absence_type."""
        _create_pending_request(db, employee, absence_type="training")
        _create_pending_request(db, employee, absence_type="vacation",
                                req_date=date(2025, 3, 13))

        resp = admin_client.get("/api/admin/vacation-requests")
        assert resp.status_code == 200
        data = resp.json()
        types = {r["absence_type"] for r in data}
        assert "training" in types
        assert "vacation" in types
