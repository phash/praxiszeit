"""Tests für die Pflicht-Pause-Ausnahme (#144, §4 ArbZG).

Nicht von §18 ArbZG befreite Mitarbeiter können einen Eintrag ohne die
gesetzlich geforderte Pause erfassen, wenn die Pause nachweislich nicht
möglich war — mit Pflicht-Begründung. Ob das eine Admin-Genehmigung
erfordert, ist pro Praxis über `break_exception_requires_approval`
konfigurierbar.

Abgedeckt:
- requires_approval=false → Eintrag wird mit Begründung gespeichert,
  ArbZG-Warnung + Audit-Log (source='break_waiver').
- Ohne Begründung → §4-Block bleibt (400).
- requires_approval=true → ChangeRequest (pending) statt Eintrag; die
  Genehmigung materialisiert den Eintrag mit gesetztem break_waiver_reason.
"""

import uuid
import pytest
from datetime import date, time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    User, UserRole, TimeEntry, TimeEntryAuditLog,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
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
    from app.routers import (
        time_entries as te_router,
        change_requests,
        admin as admin_router,
    )

    app = FastAPI(title="PraxisZeit BreakWaiver Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(te_router.router)
    app.include_router(change_requests.router)
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
        username="emp_bw",
        email="emp_bw@example.com",
        password_hash=auth_service.hash_password("test123"),
        first_name="Eva",
        last_name="Pause",
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
        username="admin_bw",
        email="admin_bw@example.com",
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


def _set_break_setting(db, value: str):
    s = SystemSetting(
        key="break_exception_requires_approval",
        tenant_id=DEFAULT_TENANT_ID,
        value=value,
        description="Pflicht-Pause-Ausnahme erfordert Genehmigung",
    )
    db.add(s)
    db.commit()


# A >9h day with no break → §4 break validation fails (needs 45min).
_LONG_DAY = {
    "date": date.today().isoformat(),
    "start_time": "07:00",
    "end_time": "17:30",  # 10.5h gross, 0 break → §4 violation AND §3 (>10h)
}
# A 7h day with no break → §4 needs 30min, but under §3 hard limit.
_OVER_6H = {
    "date": date.today().isoformat(),
    "start_time": "08:00",
    "end_time": "15:30",  # 7.5h gross, 0 break → §4 violation, under 10h
}


class TestBreakWaiverNoApproval:
    """requires_approval = false (Default)."""

    def test_no_reason_break_block_stands(self, db, employee_client):
        """Ohne Begründung bleibt der §4-Block bestehen (400)."""
        _set_break_setting(db, "false")
        resp = employee_client.post("/api/time-entries/", json={**_OVER_6H, "break_minutes": 0})
        assert resp.status_code == 400
        assert "Pause" in resp.json()["detail"]

    def test_with_reason_entry_saved_and_warning(self, db, employee, employee_client):
        """Mit Begründung wird der Eintrag gespeichert + ArbZG-Warnung zurückgegeben."""
        _set_break_setting(db, "false")
        resp = employee_client.post(
            "/api/time-entries/",
            json={**_OVER_6H, "break_minutes": 0, "break_waiver_reason": "Notfall, keine Vertretung"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["break_waiver_reason"] == "Notfall, keine Vertretung"
        # ArbZG-Warnung wird über warnings transportiert (Frontend: showArbzgWarnings)
        assert any(w.startswith("BREAK_WAIVER") for w in data["warnings"]), data["warnings"]

        # Eintrag persistiert mit Begründung
        entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
        assert entry.break_waiver_reason == "Notfall, keine Vertretung"

        # Audit-Log mit source-Marker 'break_waiver' (< 40 Zeichen)
        audit = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "break_waiver"
        ).all()
        assert len(audit) == 1
        assert len(audit[0].source) < 40

        # KEIN ChangeRequest erzeugt
        assert db.query(ChangeRequest).count() == 0

    def test_blank_reason_treated_as_missing(self, db, employee_client):
        """Eine nur aus Leerzeichen bestehende Begründung zählt nicht — §4-Block bleibt."""
        _set_break_setting(db, "false")
        resp = employee_client.post(
            "/api/time-entries/",
            json={**_OVER_6H, "break_minutes": 0, "break_waiver_reason": "   "},
        )
        assert resp.status_code == 400

    def test_valid_break_does_not_persist_waiver(self, db, employee, employee_client):
        """Wird die Pause korrekt eingehalten, bleibt break_waiver_reason NULL —
        auch wenn versehentlich eine Begründung mitgeschickt wird."""
        _set_break_setting(db, "false")
        resp = employee_client.post(
            "/api/time-entries/",
            json={**_OVER_6H, "break_minutes": 45, "break_waiver_reason": "sollte ignoriert werden"},
        )
        assert resp.status_code == 201, resp.text
        entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
        assert entry.break_waiver_reason is None


class TestBreakWaiverWithApproval:
    """requires_approval = true."""

    def test_creates_pending_change_request(self, db, employee, employee_client):
        """Bei Genehmigungspflicht entsteht ein ChangeRequest (pending), KEIN Eintrag."""
        _set_break_setting(db, "true")
        resp = employee_client.post(
            "/api/time-entries/",
            json={**_OVER_6H, "break_minutes": 0, "break_waiver_reason": "OP-Notfall"},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "pending_approval"
        assert body["change_request_id"]

        # Kein Eintrag geschrieben
        assert db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).count() == 0

        # CR pending mit Begründung als break_waiver_reason UND reason
        cr = db.query(ChangeRequest).one()
        assert cr.status == ChangeRequestStatus.PENDING
        assert cr.request_type == ChangeRequestType.CREATE
        assert cr.entry_kind == "time_entry"
        assert cr.break_waiver_reason == "OP-Notfall"
        assert cr.reason == "OP-Notfall"
        assert cr.proposed_break_minutes == 0

    def test_approval_materialises_entry_with_reason(self, db, employee, admin):
        """Die Genehmigung materialisiert den Eintrag mit gesetztem break_waiver_reason.

        Hinweis: ein einziger TestClient, dessen ``get_current_user``-Override
        zwischen Mitarbeiter und Admin umgeschaltet wird — zwei parallele
        Client-Fixtures würden sonst beide denselben App-Override mutieren und
        der MA-POST liefe versehentlich als Admin.
        """
        _set_break_setting(db, "true")

        def override_db():
            yield db

        _app.dependency_overrides[get_db] = override_db
        _app.dependency_overrides[get_current_user] = lambda: employee
        _app.dependency_overrides[require_admin] = lambda: admin
        client = TestClient(_app)
        try:
            resp = client.post(
                "/api/time-entries/",
                json={**_OVER_6H, "break_minutes": 0, "break_waiver_reason": "OP-Notfall"},
            )
            assert resp.status_code == 202, resp.text
            cr_id = resp.json()["change_request_id"]

            # Admin genehmigt (Override umschalten)
            _app.dependency_overrides[get_current_user] = lambda: admin
            review = client.post(
                f"/api/admin/change-requests/{cr_id}/review",
                json={"action": "approve"},
            )
            assert review.status_code == 200, review.text
        finally:
            _app.dependency_overrides.clear()

        cr = db.query(ChangeRequest).filter(ChangeRequest.id == uuid.UUID(cr_id)).one()
        assert cr.status == ChangeRequestStatus.APPROVED
        assert cr.reviewed_by is not None
        assert cr.reviewed_at is not None

        # Eintrag existiert jetzt mit Begründung
        entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
        assert entry.break_waiver_reason == "OP-Notfall"
        assert entry.break_minutes == 0
        assert str(cr.time_entry_id) == str(entry.id)


def _make_today_entry(db, user, break_minutes=45):
    """A compliant >6h entry for today (employees may only edit today's entries)."""
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=date.today(),
        start_time=time(8, 0),
        end_time=time(15, 30),  # 7.5h gross
        break_minutes=break_minutes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


class TestBreakWaiverUpdate:
    """Waiver auf dem UPDATE-Pfad (eigener Eintrag, heutiger Tag)."""

    def test_update_no_approval_saves_waiver(self, db, employee, employee_client):
        """requires_approval=false: Pause auf 0 reduzieren wird mit Begründung gespeichert."""
        _set_break_setting(db, "false")
        entry = _make_today_entry(db, employee, break_minutes=45)
        resp = employee_client.put(
            f"/api/time-entries/{entry.id}",
            json={"break_minutes": 0, "break_waiver_reason": "Pause entfiel kurzfristig"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["break_waiver_reason"] == "Pause entfiel kurzfristig"
        assert any(w.startswith("BREAK_WAIVER") for w in data["warnings"]), data["warnings"]
        db.refresh(entry)
        assert entry.break_minutes == 0
        assert entry.break_waiver_reason == "Pause entfiel kurzfristig"
        assert db.query(ChangeRequest).count() == 0

    def test_update_no_reason_blocks(self, db, employee, employee_client):
        """Ohne Begründung bleibt der §4-Block beim Update (400) und der Eintrag unverändert."""
        _set_break_setting(db, "false")
        entry = _make_today_entry(db, employee, break_minutes=45)
        resp = employee_client.put(
            f"/api/time-entries/{entry.id}",
            json={"break_minutes": 0},
        )
        assert resp.status_code == 400
        db.refresh(entry)
        assert entry.break_minutes == 45  # unverändert

    def test_update_with_approval_creates_cr_and_reverts(self, db, employee, employee_client):
        """requires_approval=true: UPDATE-CR (pending), Original-Eintrag bleibt unverändert."""
        _set_break_setting(db, "true")
        entry = _make_today_entry(db, employee, break_minutes=45)
        resp = employee_client.put(
            f"/api/time-entries/{entry.id}",
            json={"break_minutes": 0, "break_waiver_reason": "Notfall"},
        )
        assert resp.status_code == 202, resp.text
        # Original-Eintrag NICHT verändert
        db.refresh(entry)
        assert entry.break_minutes == 45
        assert entry.break_waiver_reason is None
        # UPDATE-CR pending mit Begründung
        cr = db.query(ChangeRequest).one()
        assert cr.status == ChangeRequestStatus.PENDING
        assert cr.request_type == ChangeRequestType.UPDATE
        assert str(cr.time_entry_id) == str(entry.id)
        assert cr.break_waiver_reason == "Notfall"
        assert cr.proposed_break_minutes == 0
        assert cr.original_break_minutes == 45


class TestDailyHardCapBeatsWaiver:
    """H1: §3 ArbZG 10h-Höchstgrenze gilt absolut — auch wenn ein Pausen-Waiver
    aktiv ist UND der Genehmigungsworkflow eingeschaltet ist. Ein >10h-Tag darf
    NIE als pending-CR (202) durchgehen, sondern muss abgelehnt werden."""

    def test_create_over_10h_with_waiver_and_approval_is_rejected(
        self, db, employee, employee_client
    ):
        """>10h + Begründung + requires_approval=true → abgelehnt (kein 202),
        KEIN ChangeRequest. Der §3-Hardcap schlägt vor der CR-Erzeugung zu."""
        _set_break_setting(db, "true")
        resp = employee_client.post(
            "/api/time-entries/",
            json={**_LONG_DAY, "break_minutes": 0, "break_waiver_reason": "Dauer-Notfall"},
        )
        # Rejected as a client error (not 202 pending_approval, not 201 created)
        assert resp.status_code != 202, resp.text
        assert resp.status_code == 422, resp.text
        assert "§3" in resp.json()["detail"]
        # Weder Eintrag noch CR dürfen entstanden sein
        assert db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).count() == 0
        assert db.query(ChangeRequest).count() == 0

    def test_create_over_10h_with_waiver_no_approval_is_rejected(
        self, db, employee, employee_client
    ):
        """Gegenprobe: auch im Nicht-Genehmigungsmodus wird >10h trotz Waiver
        abgelehnt (Regression-Schutz für den direkten Pfad)."""
        _set_break_setting(db, "false")
        resp = employee_client.post(
            "/api/time-entries/",
            json={**_LONG_DAY, "break_minutes": 0, "break_waiver_reason": "Dauer-Notfall"},
        )
        assert resp.status_code == 422, resp.text
        assert "§3" in resp.json()["detail"]
        assert db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).count() == 0


class TestBreakWaiverSelfApprovalForbidden:
    """SEC-E: 4-Augen-Prinzip — ein Admin darf seine EIGENE Pflicht-Pause-
    Ausnahme nicht selbst genehmigen."""

    def test_admin_cannot_self_approve_own_waiver_cr(self, db, admin):
        """Admin reicht selbst einen Waiver-CR ein und versucht, ihn selbst zu
        genehmigen → 403. Der CR bleibt pending."""
        _set_break_setting(db, "true")

        def override_db():
            yield db

        _app.dependency_overrides[get_db] = override_db
        # Admin agiert als Antragsteller UND Genehmiger (= dieselbe Person)
        _app.dependency_overrides[get_current_user] = lambda: admin
        _app.dependency_overrides[require_admin] = lambda: admin
        client = TestClient(_app)
        try:
            resp = client.post(
                "/api/time-entries/",
                json={**_OVER_6H, "break_minutes": 0, "break_waiver_reason": "Eigener Notfall"},
            )
            assert resp.status_code == 202, resp.text
            cr_id = resp.json()["change_request_id"]

            review = client.post(
                f"/api/admin/change-requests/{cr_id}/review",
                json={"action": "approve"},
            )
            assert review.status_code == 403, review.text
            assert "selbst genehmigt" in review.json()["detail"]
        finally:
            _app.dependency_overrides.clear()

        cr = db.query(ChangeRequest).filter(ChangeRequest.id == uuid.UUID(cr_id)).one()
        assert cr.status == ChangeRequestStatus.PENDING
        assert cr.reviewed_by is None

    def test_admin_can_approve_other_users_waiver_cr(self, db, employee, admin):
        """Gegenprobe: ein FREMDER Waiver-CR (vom MA) darf vom Admin genehmigt
        werden — das 4-Augen-Prinzip blockiert nur Selbstgenehmigung."""
        _set_break_setting(db, "true")

        def override_db():
            yield db

        _app.dependency_overrides[get_db] = override_db
        _app.dependency_overrides[get_current_user] = lambda: employee
        _app.dependency_overrides[require_admin] = lambda: admin
        client = TestClient(_app)
        try:
            resp = client.post(
                "/api/time-entries/",
                json={**_OVER_6H, "break_minutes": 0, "break_waiver_reason": "MA-Notfall"},
            )
            assert resp.status_code == 202, resp.text
            cr_id = resp.json()["change_request_id"]

            _app.dependency_overrides[get_current_user] = lambda: admin
            review = client.post(
                f"/api/admin/change-requests/{cr_id}/review",
                json={"action": "approve"},
            )
            assert review.status_code == 200, review.text
        finally:
            _app.dependency_overrides.clear()

        cr = db.query(ChangeRequest).filter(ChangeRequest.id == uuid.UUID(cr_id)).one()
        assert cr.status == ChangeRequestStatus.APPROVED
