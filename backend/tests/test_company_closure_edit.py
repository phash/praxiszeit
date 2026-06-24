"""Tests for editable Betriebsferien (#142): PUT re-sync + closure_id FK linkage.

Covers:
- PUT extends the range -> absences for newly covered workdays are added.
- PUT shrinks the range -> absences for dropped days are removed, others kept.
- delete via closure_id removes exactly the linked absences (even after a rename).
- Foreign absences (other types / manually created) stay untouched.
- Tenant isolation: a closure of tenant A is invisible / uneditable for tenant B.
"""

import uuid
import pytest
from datetime import date
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType, CompanyClosure
from app.models.tenant import Tenant
from tests.conftest import (
    DEFAULT_TENANT_ID,
    engine,
    TestingSessionLocal,
)

# A second tenant for isolation tests.
OTHER_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000ff")

# A clean Mon-Fri work week in March 2025 with no public holidays seeded.
MON = date(2025, 3, 10)
TUE = date(2025, 3, 11)
WED = date(2025, 3, 12)
THU = date(2025, 3, 13)
FRI = date(2025, 3, 14)
# Following Monday (used for range extension).
NEXT_MON = date(2025, 3, 17)
NEXT_TUE = date(2025, 3, 18)


# ---------------------------------------------------------------------------
# Test app setup
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    from app.routers import company_closures

    app = FastAPI(title="PraxisZeit Closure Edit Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


def _make_tenant(db, tenant_id, slug):
    tenant = Tenant(
        id=tenant_id,
        name=slug.capitalize(),
        slug=slug,
        is_active=True,
        mode="single",
    )
    db.add(tenant)
    db.commit()
    return tenant


@pytest.fixture
def default_tenant(db):
    return _make_tenant(db, DEFAULT_TENANT_ID, "default")


@pytest.fixture
def other_tenant(db):
    return _make_tenant(db, OTHER_TENANT_ID, "other")


def _make_user(db, tenant_id, username, role=UserRole.EMPLOYEE):
    from app.services import auth_service
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=auth_service.hash_password("test123"),
        first_name=username,
        last_name="Test",
        role=role,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def employee(db, default_tenant):
    return _make_user(db, DEFAULT_TENANT_ID, "emp1")


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, DEFAULT_TENANT_ID, "admin1", role=UserRole.ADMIN)


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


def _create_closure(client, name, start, end):
    resp = client.post("/api/company-closures/", json={
        "name": name,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _closure_absences(db, employee, closure_id):
    return db.query(Absence).filter(
        Absence.user_id == employee.id,
        Absence.closure_id == uuid.UUID(closure_id),
    ).order_by(Absence.date).all()


# ---------------------------------------------------------------------------
# closure_id linkage on create
# ---------------------------------------------------------------------------

class TestCreateLinksClosureId:
    def test_create_sets_closure_id(self, db, employee, admin_client):
        """Prüft dass beim Anlegen erzeugte Absences den closure_id-FK gesetzt bekommen."""
        closure = _create_closure(admin_client, "Ostern 2025", MON, WED)

        absences = _closure_absences(db, employee, closure["id"])
        assert {a.date for a in absences} == {MON, TUE, WED}
        for a in absences:
            assert a.closure_id == uuid.UUID(closure["id"])
            assert a.type == AbsenceType.VACATION
            assert a.note == "Betriebsferien: Ostern 2025"


# ---------------------------------------------------------------------------
# PUT: extend range
# ---------------------------------------------------------------------------

class TestPutExtendsRange:
    def test_extending_adds_absences_for_new_workdays(self, db, employee, admin_client):
        """Prüft dass Verlängern des Zeitraums Absences für neue Arbeitstage erzeugt (REQ-2)."""
        closure = _create_closure(admin_client, "Sommer", MON, TUE)
        assert {a.date for a in _closure_absences(db, employee, closure["id"])} == {MON, TUE}

        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Sommer",
            "start_date": MON.isoformat(),
            "end_date": THU.isoformat(),
        })
        assert resp.status_code == 200, resp.text

        absences = _closure_absences(db, employee, closure["id"])
        assert {a.date for a in absences} == {MON, TUE, WED, THU}
        # end_date of all linked absences updated to the new range end.
        assert all(a.end_date == THU for a in absences)

    def test_extending_into_next_week_skips_weekend(self, db, employee, admin_client):
        """Prüft dass beim Verlängern über das Wochenende nur Werktage Absences bekommen."""
        closure = _create_closure(admin_client, "Sommer", THU, FRI)
        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Sommer",
            "start_date": THU.isoformat(),
            "end_date": NEXT_TUE.isoformat(),
        })
        assert resp.status_code == 200, resp.text
        # Sat 15 + Sun 16 are skipped.
        assert {a.date for a in _closure_absences(db, employee, closure["id"])} == {
            THU, FRI, NEXT_MON, NEXT_TUE,
        }


# ---------------------------------------------------------------------------
# PUT: shrink range
# ---------------------------------------------------------------------------

class TestPutShrinksRange:
    def test_shrinking_removes_dropped_day_absences(self, db, employee, admin_client):
        """Prüft dass Verkürzen des Zeitraums die Absences entfallener Tage löscht (REQ-2)."""
        closure = _create_closure(admin_client, "Winter", MON, FRI)
        assert {a.date for a in _closure_absences(db, employee, closure["id"])} == {
            MON, TUE, WED, THU, FRI,
        }

        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Winter",
            "start_date": MON.isoformat(),
            "end_date": TUE.isoformat(),
        })
        assert resp.status_code == 200, resp.text

        absences = _closure_absences(db, employee, closure["id"])
        assert {a.date for a in absences} == {MON, TUE}
        # The dropped days have no leftover absence at all.
        assert db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == WED,
        ).count() == 0


# ---------------------------------------------------------------------------
# PUT: rename
# ---------------------------------------------------------------------------

class TestPutRename:
    def test_rename_updates_linked_absence_notes(self, db, employee, admin_client):
        """Prüft dass eine Umbenennung die note der verknüpften Absences mitzieht."""
        closure = _create_closure(admin_client, "Falscher Name", MON, TUE)

        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Korrekter Name",
            "start_date": MON.isoformat(),
            "end_date": TUE.isoformat(),
        })
        assert resp.status_code == 200, resp.text

        absences = _closure_absences(db, employee, closure["id"])
        assert {a.note for a in absences} == {"Betriebsferien: Korrekter Name"}


# ---------------------------------------------------------------------------
# PUT: foreign absences untouched
# ---------------------------------------------------------------------------

class TestForeignAbsencesUntouched:
    def test_extend_skips_day_with_foreign_absence(self, db, employee, admin_client):
        """Prüft dass beim Verlängern ein Tag mit bestehender Fremd-Absence nicht überschrieben wird."""
        # Pre-existing SICK absence on WED (will be inside the extended range).
        sick = Absence(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=WED,
            type=AbsenceType.SICK,
            hours=8.0,
        )
        db.add(sick)
        db.commit()

        closure = _create_closure(admin_client, "Sommer", MON, TUE)
        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Sommer",
            "start_date": MON.isoformat(),
            "end_date": THU.isoformat(),
        })
        assert resp.status_code == 200, resp.text

        # WED stays SICK and is NOT linked to the closure.
        wed_absences = db.query(Absence).filter(
            Absence.user_id == employee.id,
            Absence.date == WED,
        ).all()
        assert len(wed_absences) == 1
        assert wed_absences[0].type == AbsenceType.SICK
        assert wed_absences[0].closure_id is None

        # Closure covers MON, TUE, THU (WED skipped).
        assert {a.date for a in _closure_absences(db, employee, closure["id"])} == {
            MON, TUE, THU,
        }


# ---------------------------------------------------------------------------
# DELETE via closure_id
# ---------------------------------------------------------------------------

class TestDeleteViaClosureId:
    def test_delete_removes_linked_absences(self, db, employee, admin_client):
        """Prüft dass Löschen über closure_id genau die verknüpften Absences entfernt."""
        closure = _create_closure(admin_client, "Sommer", MON, WED)
        assert _closure_absences(db, employee, closure["id"])

        resp = admin_client.delete(f"/api/company-closures/{closure['id']}")
        assert resp.status_code == 204

        assert db.query(Absence).filter(
            Absence.user_id == employee.id,
        ).count() == 0
        assert db.query(CompanyClosure).count() == 0

    def test_delete_after_rename_still_removes_absences(self, db, employee, admin_client):
        """Prüft dass Löschen auch nach Umbenennung greift (FK statt Note-String, REQ-3)."""
        closure = _create_closure(admin_client, "Alter Name", MON, WED)

        # Rename via PUT -> notes change, but closure_id stays.
        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Neuer Name",
            "start_date": MON.isoformat(),
            "end_date": WED.isoformat(),
        })
        assert resp.status_code == 200, resp.text

        resp = admin_client.delete(f"/api/company-closures/{closure['id']}")
        assert resp.status_code == 204

        # The note-string match would have missed these (old name) — FK does not.
        assert db.query(Absence).filter(
            Absence.user_id == employee.id,
        ).count() == 0

    def test_delete_keeps_foreign_absences(self, db, employee, admin_client):
        """Prüft dass Löschen Fremd-Absences im Zeitraum unberührt lässt."""
        # Foreign SICK absence on WED, before creating a closure that skips it.
        sick = Absence(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=WED,
            type=AbsenceType.SICK,
            hours=8.0,
        )
        db.add(sick)
        db.commit()

        closure = _create_closure(admin_client, "Sommer", MON, THU)
        resp = admin_client.delete(f"/api/company-closures/{closure['id']}")
        assert resp.status_code == 204

        remaining = db.query(Absence).filter(
            Absence.user_id == employee.id,
        ).all()
        assert len(remaining) == 1
        assert remaining[0].type == AbsenceType.SICK
        assert remaining[0].date == WED


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_put_other_tenant_closure_is_404(self, db, default_tenant, other_tenant):
        """Prüft dass ein Closure aus Tenant A für Tenant B nicht editierbar ist (404)."""
        admin_a = _make_user(db, DEFAULT_TENANT_ID, "admin_a", role=UserRole.ADMIN)
        admin_b = _make_user(db, OTHER_TENANT_ID, "admin_b", role=UserRole.ADMIN)

        # Closure created by tenant A.
        client_a = next(_make_client(db, admin_a))
        closure = _create_closure(client_a, "A-Ferien", MON, TUE)
        _app.dependency_overrides.clear()

        # Tenant B tries to edit it -> 404.
        client_b = next(_make_client(db, admin_b))
        resp = client_b.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Hijack",
            "start_date": MON.isoformat(),
            "end_date": WED.isoformat(),
        })
        _app.dependency_overrides.clear()
        assert resp.status_code == 404

    def test_delete_other_tenant_closure_is_404(self, db, default_tenant, other_tenant):
        """Prüft dass ein Closure aus Tenant A für Tenant B nicht löschbar ist (404)."""
        admin_a = _make_user(db, DEFAULT_TENANT_ID, "admin_a", role=UserRole.ADMIN)
        admin_b = _make_user(db, OTHER_TENANT_ID, "admin_b", role=UserRole.ADMIN)

        client_a = next(_make_client(db, admin_a))
        closure = _create_closure(client_a, "A-Ferien", MON, TUE)
        _app.dependency_overrides.clear()

        client_b = next(_make_client(db, admin_b))
        resp = client_b.delete(f"/api/company-closures/{closure['id']}")
        _app.dependency_overrides.clear()
        assert resp.status_code == 404

        # Closure still exists.
        assert db.query(CompanyClosure).filter(
            CompanyClosure.id == uuid.UUID(closure["id"]),
        ).count() == 1


# ---------------------------------------------------------------------------
# #290: re-saving a closure must NEVER delete a participant's logged work
# ---------------------------------------------------------------------------

class TestResavePreservesTimeEntries:
    def test_resave_does_not_delete_logged_time_entry(self, db, admin, admin_client):
        """Regression #290: an employee who logged real work on a covered day
        (because they had no closure-absence — e.g. onboarded after creation)
        must keep that TimeEntry when the closure is re-saved. Re-save was the
        documented #290 workaround and silently destroyed worked time."""
        from datetime import time
        from app.models import TimeEntry, TimeEntryAuditLog

        emp1 = _make_user(db, DEFAULT_TENANT_ID, "emp_keep_a")
        closure = _create_closure(admin_client, "Betriebsferien", MON, WED)

        # A second employee, created AFTER the closure -> no closure-absence for them.
        emp2 = _make_user(db, DEFAULT_TENANT_ID, "emp_keep_b")
        te = TimeEntry(
            user_id=emp2.id, tenant_id=DEFAULT_TENANT_ID, date=TUE,
            start_time=time(8, 0), end_time=time(16, 0), break_minutes=30,
        )
        db.add(te)
        db.commit()
        te_id = te.id

        # Re-save the UNCHANGED closure (the #290 "Betroffene aktualisieren" workaround).
        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Betriebsferien",
            "start_date": MON.isoformat(),
            "end_date": WED.isoformat(),
            "counts_as_vacation": True,
        })
        assert resp.status_code == 200, resp.text

        survived = db.query(TimeEntry).filter(TimeEntry.id == te_id).first()
        assert survived is not None, "re-save deleted a real time entry (#290 data loss!)"
        # And no closure-absence was booked over the worked day (work wins).
        booked = db.query(Absence).filter(
            Absence.user_id == emp2.id, Absence.date == TUE,
            Absence.closure_id == uuid.UUID(closure["id"]),
        ).count()
        assert booked == 0, "closure-absence booked over a logged work day"

    def test_create_still_clears_time_entries(self, db, admin, admin_client):
        """CREATE keeps its original behaviour: a closure replaces pre-existing
        time entries on covered days (deliberate first-time action)."""
        from datetime import time
        from app.models import TimeEntry

        emp = _make_user(db, DEFAULT_TENANT_ID, "emp_create_clear")
        te = TimeEntry(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=TUE,
            start_time=time(8, 0), end_time=time(16, 0), break_minutes=30,
        )
        db.add(te)
        db.commit()
        te_id = te.id

        _create_closure(admin_client, "Neue Ferien", MON, WED)

        # On create, the worked entry is replaced by the closure absence (legacy intent).
        assert db.query(TimeEntry).filter(TimeEntry.id == te_id).first() is None


# ---------------------------------------------------------------------------
# #290: a newly created participating employee is auto-enrolled into existing
# current/future closures (no destructive re-save needed); PAST closures are not.
# ---------------------------------------------------------------------------

class TestNewUserEnrolledInOpenClosures:
    def test_enroll_current_future_not_past(self, db, admin):
        from datetime import timedelta
        from app.models import CompanyClosure
        from app.routers.admin_users import _enroll_user_in_open_closures

        today = date.today()
        fut = CompanyClosure(
            name="Sommer", start_date=today + timedelta(days=7),
            end_date=today + timedelta(days=13), counts_as_vacation=True,
            created_by=admin.id, tenant_id=DEFAULT_TENANT_ID,
        )
        past = CompanyClosure(
            name="Winter alt", start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=24), counts_as_vacation=True,
            created_by=admin.id, tenant_id=DEFAULT_TENANT_ID,
        )
        db.add_all([fut, past])
        db.commit()

        emp = User(
            username="emp_enroll", email="emp_enroll@example.com",
            password_hash="x", first_name="E", last_name="E",
            role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
            work_days_per_week=5, is_active=True,
            receives_company_closures=True, tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)

        _enroll_user_in_open_closures(db, emp, admin)
        db.commit()

        fut_abs = db.query(Absence).filter(
            Absence.user_id == emp.id, Absence.closure_id == fut.id,
        ).count()
        past_abs = db.query(Absence).filter(
            Absence.user_id == emp.id, Absence.closure_id == past.id,
        ).count()
        assert fut_abs > 0, "#290: new employee not enrolled in current/future closure"
        assert past_abs == 0, "#290: new employee wrongly backfilled into a PAST closure"
