"""Tests for TimeEntry cleanup when creating absences (F1, F2, F3).

F1: Direct absence creation (POST /absences) deletes existing TimeEntries.
F2: Company closures delete existing TimeEntries.
F3: Company closures skip days with ANY existing absence (not just vacation).
"""

import uuid
import pytest
from datetime import date, time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TimeEntry, Absence, AbsenceType, TimeEntryAuditLog
from app.models import PublicHoliday, CompanyClosure
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from tests.conftest import (
    DEFAULT_TENANT_ID,
    engine,
    TestingSessionLocal,
)


# ---------------------------------------------------------------------------
# Test app setup
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    from app.routers import absences, company_closures

    app = FastAPI(title="PraxisZeit Cleanup Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(absences.router)
    app.include_router(company_closures.router)

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


@pytest.fixture
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


@pytest.fixture
def employee(db, default_tenant):
    from app.services import auth_service
    user = User(
        username="emp1",
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


@pytest.fixture
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


def _create_time_entry(db, user, entry_date, start_h=8, end_h=16, break_min=30):
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=entry_date,
        start_time=time(start_h, 0),
        end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# F1: Direct absence creation deletes TimeEntries
# ---------------------------------------------------------------------------

class TestF1_DirectAbsenceDeletesTimeEntries:
    """POST /absences löscht bestehende TimeEntries."""

    def test_training_absence_deletes_time_entry(self, db, employee, admin, admin_client):
        """Fortbildungs-Absence löscht bestehenden TimeEntry."""
        _create_time_entry(db, employee, date(2025, 3, 12))

        resp = admin_client.post("/api/absences/", json={
            "user_id": str(employee.id),
            "date": "2025-03-12",
            "type": "training",
            "hours": 8.0,
        })
        assert resp.status_code == 201

        # TimeEntry deleted
        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id,
            TimeEntry.date == date(2025, 3, 12),
        ).count() == 0

        # Absence created
        assert db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 12),
            Absence.type == AbsenceType.TRAINING,
        ).count() == 1

    def test_vacation_absence_deletes_time_entry(self, db, employee, admin, admin_client):
        """Urlaubs-Absence löscht bestehenden TimeEntry."""
        _create_time_entry(db, employee, date(2025, 3, 12))

        resp = admin_client.post("/api/absences/", json={
            "user_id": str(employee.id),
            "date": "2025-03-12",
            "type": "vacation",
            "hours": 8.0,
        })
        assert resp.status_code == 201

        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id,
            TimeEntry.date == date(2025, 3, 12),
        ).count() == 0

    def test_deletion_creates_audit_log(self, db, employee, admin, admin_client):
        """Gelöschte TimeEntries erzeugen Audit-Log."""
        entry = _create_time_entry(db, employee, date(2025, 3, 12))
        entry_id = entry.id

        resp = admin_client.post("/api/absences/", json={
            "user_id": str(employee.id),
            "date": "2025-03-12",
            "type": "training",
            "hours": 8.0,
        })
        assert resp.status_code == 201

        audit = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.time_entry_id == entry_id,
            TimeEntryAuditLog.action == "delete",
        ).first()
        assert audit is not None
        assert audit.source == "absence_creation"

    def test_no_time_entry_no_error(self, db, employee, admin, admin_client):
        """Keine bestehenden TimeEntries → kein Fehler."""
        resp = admin_client.post("/api/absences/", json={
            "user_id": str(employee.id),
            "date": "2025-03-12",
            "type": "training",
            "hours": 8.0,
        })
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# F2 + F3: Company closures
# ---------------------------------------------------------------------------

class TestF2_ClosureDeletesTimeEntries:
    """Betriebsferien löschen bestehende TimeEntries."""

    def test_closure_deletes_time_entries(self, db, employee, admin, admin_client):
        """TimeEntries an Betriebsferien-Tagen werden gelöscht."""
        # Wednesday 2025-03-12
        _create_time_entry(db, employee, date(2025, 3, 12))

        resp = admin_client.post("/api/company-closures/", json={
            "name": "Brückentag",
            "start_date": "2025-03-12",
            "end_date": "2025-03-12",
        })
        assert resp.status_code == 201

        # TimeEntry deleted
        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id,
            TimeEntry.date == date(2025, 3, 12),
        ).count() == 0

        # Absence created
        assert db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 12),
            Absence.type == AbsenceType.VACATION,
        ).count() == 1

    def test_closure_audit_log(self, db, employee, admin, admin_client):
        """Closure-Löschungen erzeugen Audit-Log mit source=company_closure."""
        entry = _create_time_entry(db, employee, date(2025, 3, 12))
        entry_id = entry.id

        resp = admin_client.post("/api/company-closures/", json={
            "name": "Brückentag",
            "start_date": "2025-03-12",
            "end_date": "2025-03-12",
        })
        assert resp.status_code == 201

        audit = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.time_entry_id == entry_id,
            TimeEntryAuditLog.action == "delete",
        ).first()
        assert audit is not None
        assert audit.source == "company_closure"


class TestF3_ClosureSkipsAllAbsenceTypes:
    """Betriebsferien überspringen Tage mit beliebigen Absences."""

    def test_closure_skips_training_absence(self, db, employee, admin, admin_client):
        """Tag mit Training-Absence wird bei Betriebsferien übersprungen."""
        # Create existing TRAINING absence
        training = Absence(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=date(2025, 3, 12),
            type=AbsenceType.TRAINING,
            hours=8.0,
            note="Fortbildung",
        )
        db.add(training)
        db.commit()

        resp = admin_client.post("/api/company-closures/", json={
            "name": "Brückentag",
            "start_date": "2025-03-12",
            "end_date": "2025-03-12",
        })
        assert resp.status_code == 201

        # No duplicate VACATION created — only original TRAINING remains
        absences = db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 12),
        ).all()
        assert len(absences) == 1
        assert absences[0].type == AbsenceType.TRAINING

    def test_closure_skips_sick_absence(self, db, employee, admin, admin_client):
        """Tag mit Sick-Absence wird bei Betriebsferien übersprungen."""
        sick = Absence(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=date(2025, 3, 12),
            type=AbsenceType.SICK,
            hours=8.0,
        )
        db.add(sick)
        db.commit()

        resp = admin_client.post("/api/company-closures/", json={
            "name": "Brückentag",
            "start_date": "2025-03-12",
            "end_date": "2025-03-12",
        })
        assert resp.status_code == 201

        absences = db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == date(2025, 3, 12),
        ).all()
        assert len(absences) == 1
        assert absences[0].type == AbsenceType.SICK
