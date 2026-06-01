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
from datetime import date, time, timedelta
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

# CR-Variante (proposed_*-Keys) eines §4-verletzenden Eintrags.
_CR_OVER_6H = {
    "request_type": "create",
    "proposed_date": (date.today() - timedelta(days=7)).isoformat(),  # vergangener Werktag
    "proposed_start_time": "08:00",
    "proposed_end_time": "15:46",  # 7h46m brutto, 0 Pause → §4-Verstoß, unter 10h
    "proposed_break_minutes": 0,
    "reason": "Korrektur Zeiteintrag",
}


class TestChangeRequestBreakWaiver:
    """#200: Die §4-Pausen-Ausnahme muss auch im Änderungsantrag-Pfad greifen
    (vorher: break_waiver_reason wurde ignoriert → 400 trotz korrekter Eingabe)."""

    def test_cr_without_waiver_blocked(self, db, employee_client):
        """Ohne Begründung bleibt der §4-Block (400) — Kontrolle."""
        resp = employee_client.post("/api/change-requests/", json=_CR_OVER_6H)
        assert resp.status_code == 400
        assert "Pause" in resp.json()["detail"]

    def test_cr_with_waiver_created(self, db, employee, employee_client):
        """Mit Begründung wird der Antrag angelegt (201) statt abgewiesen."""
        resp = employee_client.post(
            "/api/change-requests/",
            json={**_CR_OVER_6H, "break_waiver_reason": "Notfall, keine Vertretung"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["break_waiver_reason"] == "Notfall, keine Vertretung"
        cr = db.query(ChangeRequest).filter(ChangeRequest.user_id == employee.id).one()
        assert cr.break_waiver_reason == "Notfall, keine Vertretung"

    def test_cr_waiver_still_blocks_over_10h(self, db, employee_client):
        """§3-10h-Cap bleibt hart, auch MIT §4-Ausnahme (422, nicht 201)."""
        resp = employee_client.post(
            "/api/change-requests/",
            json={**_CR_OVER_6H, "proposed_end_time": "19:00", "break_waiver_reason": "egal"},
        )
        assert resp.status_code == 422, resp.text


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

    def test_admin_cannot_approve_own_break_waiver_cr(self, db, admin, admin_client):
        """SEC-E (regression): the 4-eyes guard forbids an admin approving their
        OWN documented break-exception. Previously only the cross-user happy
        path was covered."""
        cr = ChangeRequest(
            user_id=admin.id,  # the approving admin is also the requester
            tenant_id=DEFAULT_TENANT_ID,
            request_type=ChangeRequestType.CREATE,
            entry_kind="time_entry",
            status=ChangeRequestStatus.PENDING,
            proposed_date=date.today(),
            proposed_start_time=time(8, 0),
            proposed_end_time=time(15, 30),
            proposed_break_minutes=0,
            break_waiver_reason="Selbst dokumentiert",
            reason="Selbst dokumentiert",
        )
        db.add(cr)
        db.commit()
        db.refresh(cr)

        resp = admin_client.post(
            f"/api/admin/change-requests/{cr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 403, resp.text
        assert "selbst genehmigt" in resp.json()["detail"].lower()

        # CR stays pending, no entry materialised.
        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.PENDING
        assert db.query(TimeEntry).filter(TimeEntry.user_id == admin.id).count() == 0

    def test_approval_revalidates_section3_against_current_db(self, db, employee, admin, admin_client):
        """C-1 (regression, TOCTOU): a CREATE CR that was valid in isolation must
        be rejected at approval when other same-day entries have since pushed the
        day over the §3 10h hard cap. The §3 ceiling is absolute and unwaivable."""
        # An entry already exists on the day: 08:00–16:00, 30 min break → 7.5h net.
        existing = TimeEntry(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=date.today(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            break_minutes=30,
        )
        db.add(existing)
        db.commit()

        # Pending CREATE CR proposing a SECOND entry 16:30–22:00 (5.5h, no break).
        # In isolation it is fine; combined with the existing 7.5h the day is 13h > 10h.
        cr = ChangeRequest(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            request_type=ChangeRequestType.CREATE,
            entry_kind="time_entry",
            status=ChangeRequestStatus.PENDING,
            proposed_date=date.today(),
            proposed_start_time=time(16, 30),
            proposed_end_time=time(22, 0),
            proposed_break_minutes=0,
            reason="Zweiter Block",
        )
        db.add(cr)
        db.commit()
        db.refresh(cr)

        resp = admin_client.post(
            f"/api/admin/change-requests/{cr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 422, resp.text
        assert "§3" in resp.json()["detail"]

        # CR stays pending; the proposed entry was NOT materialised.
        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.PENDING
        assert db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).count() == 1


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


class TestCrApprovalRevalidatesDailyHardCap:
    """C-1: a CREATE/UPDATE ChangeRequest is re-validated against the CURRENT DB
    state on approval. A CR that was valid (≤10h) at creation time but would,
    together with same-day entries added since, push the day over the §3 10h
    ceiling MUST be rejected with 422 — the entry is NOT written and the CR
    stays PENDING."""

    def test_approve_create_cr_pushing_day_over_10h_is_rejected(
        self, db, employee, admin
    ):
        past_day = date.today() - timedelta(days=3)
        # Move past_day to a weekday so day-of-week edge cases don't matter
        # (irrelevant for §3, but keeps the scenario realistic).
        while past_day.weekday() >= 5:
            past_day -= timedelta(days=1)

        # A pending CREATE CR: 07:00–14:00, 0 break → 7.0h net, valid on its own
        # (under §3, and §4 30-min rule is excused via break_waiver_reason so the
        # CR could legitimately exist; we only test the §3 re-check here).
        cr = ChangeRequest(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            request_type=ChangeRequestType.CREATE,
            entry_kind="time_entry",
            status=ChangeRequestStatus.PENDING,
            proposed_date=past_day,
            proposed_start_time=time(7, 0),
            proposed_end_time=time(14, 0),  # 7.0h net
            proposed_break_minutes=0,
            reason="Nachtrag",
            break_waiver_reason="Pause entfiel",  # excuses §4, not §3
        )
        db.add(cr)

        # Meanwhile, a same-day entry was added that already accounts for 5h.
        # Approving the CR would make the day 7 + 5 = 12h → over the 10h cap.
        existing = TimeEntry(
            user_id=employee.id,
            tenant_id=DEFAULT_TENANT_ID,
            date=past_day,
            start_time=time(15, 0),
            end_time=time(20, 0),  # 5.0h net
            break_minutes=0,
        )
        db.add(existing)
        db.commit()
        db.refresh(cr)
        cr_id = cr.id

        def override_db():
            yield db

        _app.dependency_overrides[get_db] = override_db
        _app.dependency_overrides[get_current_user] = lambda: admin
        _app.dependency_overrides[require_admin] = lambda: admin
        client = TestClient(_app)
        try:
            review = client.post(
                f"/api/admin/change-requests/{cr_id}/review",
                json={"action": "approve"},
            )
            assert review.status_code == 422, review.text
            assert "§3" in review.json()["detail"]
        finally:
            _app.dependency_overrides.clear()

        # CR must still be PENDING and NO new entry written (only the seeded one)
        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.PENDING
        assert cr.reviewed_by is None
        entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == employee.id, TimeEntry.date == past_day
        ).all()
        assert len(entries) == 1  # only the pre-existing same-day entry


class TestClockOutBreakWaiver:
    """Review 2026-05-29 (M-ARB1): the clock-out path must accept a
    break_waiver_reason so a §4 deviation during stamping is documented
    (entry field + audit source='break_waiver'), not merely warned."""

    def _open_entry(self, db, employee, today, start=time(8, 0)):
        e = TimeEntry(
            user_id=employee.id, tenant_id=DEFAULT_TENANT_ID,
            date=today, start_time=start, end_time=None, break_minutes=0,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        return e

    def _freeze(self, monkeypatch):
        import app.routers.time_entries as te
        from datetime import datetime
        today = date.today()
        fixed_now = datetime(today.year, today.month, today.day, 15, 30, tzinfo=te.LOCAL_TZ)
        monkeypatch.setattr(te, "_now_local", lambda: fixed_now)
        monkeypatch.setattr(te, "_today_local", lambda: today)
        return today

    def test_clock_out_records_break_waiver(self, db, employee, employee_client, monkeypatch):
        today = self._freeze(monkeypatch)
        self._open_entry(db, employee, today)  # 08:00 → 15:30 = 7.5h, 0 break → §4

        resp = employee_client.post("/api/time-entries/clock-out", json={
            "break_minutes": 0,
            "break_waiver_reason": "Akuter Notfall, keine Pause möglich",
        })
        assert resp.status_code == 200, resp.text
        db.expire_all()
        entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).first()
        assert entry.break_waiver_reason == "Akuter Notfall, keine Pause möglich"
        audit = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "break_waiver"
        ).all()
        assert len(audit) >= 1
        warnings = resp.json().get("warnings", [])
        assert any("BREAK_WAIVER" in w for w in warnings), warnings

    def test_clock_out_without_reason_still_warns(self, db, employee, employee_client, monkeypatch):
        today = self._freeze(monkeypatch)
        self._open_entry(db, employee, today)

        resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0})
        assert resp.status_code == 200, resp.text
        db.expire_all()
        entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).first()
        assert entry.break_waiver_reason is None
        warnings = resp.json().get("warnings", [])
        assert any("BREAK_WARNING" in w for w in warnings), warnings


class TestAdminBreakWaiverParity:
    """Review 2026-05-29 (M-ARB3): the admin direct-entry paths must offer the
    same documented §4 break-waiver as the employee path (#144) — record the
    reason + audit (source='break_waiver') instead of a hard 400."""

    def test_admin_create_with_waiver_records_it(self, db, employee, admin_client):
        payload = {**_OVER_6H, "break_minutes": 0, "break_waiver_reason": "Notfalleinsatz"}
        resp = admin_client.post(f"/api/admin/users/{employee.id}/time-entries", json=payload)
        assert resp.status_code == 201, resp.text
        db.expire_all()
        entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).first()
        assert entry.break_waiver_reason == "Notfalleinsatz"
        audit = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "break_waiver"
        ).all()
        assert len(audit) >= 1
        assert any("BREAK_WAIVER" in w for w in resp.json().get("warnings", []))

    def test_admin_create_without_waiver_still_blocks(self, db, employee, admin_client):
        payload = {**_OVER_6H, "break_minutes": 0}
        resp = admin_client.post(f"/api/admin/users/{employee.id}/time-entries", json=payload)
        assert resp.status_code == 400, resp.text

    def test_admin_update_with_waiver_records_it(self, db, employee, admin_client):
        # Pre-existing compliant entry (30min break on a 7.5h day).
        entry = TimeEntry(
            user_id=employee.id, tenant_id=DEFAULT_TENANT_ID,
            date=date.today(), start_time=time(8, 0), end_time=time(15, 30),
            break_minutes=30,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        resp = admin_client.put(
            f"/api/admin/time-entries/{entry.id}",
            json={"break_minutes": 0, "break_waiver_reason": "Notfalleinsatz"},
        )
        assert resp.status_code == 200, resp.text
        db.expire_all()
        refreshed = db.query(TimeEntry).filter(TimeEntry.id == entry.id).first()
        assert refreshed.break_waiver_reason == "Notfalleinsatz"
        audit = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "break_waiver"
        ).all()
        assert len(audit) >= 1
