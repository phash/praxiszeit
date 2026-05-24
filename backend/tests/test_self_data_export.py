"""Tests fuer DSGVO Art. 15 Self-Service-Export (Issue #119).

Endpoint: GET /api/me/data-export
"""

import json
from datetime import date, time, timedelta
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user
from app.models import (
    Absence,
    AbsenceType,
    ChangeRequest,
    TimeEntry,
    TimeEntryAuditLog,
    User,
    UserRole,
    VacationRequest,
)
from app.models.tenant import Tenant
from app.models.vacation_request import VacationRequestStatus
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


SECOND_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _create_test_app() -> FastAPI:
    from app.routers import me

    app = FastAPI(title="PraxisZeit SelfExport Test")
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(me.router)
    return app


_app = _create_test_app()


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
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


@pytest.fixture
def second_tenant(db):
    t = Tenant(id=SECOND_TENANT_ID, name="Second", slug="second", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, username, tenant_id=None, role=UserRole.EMPLOYEE):
    from app.services import auth_service
    u = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=auth_service.hash_password("x"),
        first_name=username.title(),
        last_name="Test",
        role=role,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=tenant_id or DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_client(db_session, current_user):
    def override_db():
        yield db_session
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(_app)
    yield client
    _app.dependency_overrides.clear()


@pytest.fixture
def alice(db, default_tenant):
    return _user(db, "alice")


@pytest.fixture
def bob(db, default_tenant):
    return _user(db, "bob")


@pytest.fixture
def carol_other_tenant(db, second_tenant):
    return _user(db, "carol", tenant_id=SECOND_TENANT_ID)


@pytest.fixture
def alice_client(db, alice):
    yield from _make_client(db, alice)


def _make_data(db, user, *, entries=2, absences=1, vacations=1, change_requests=0):
    """Befuelle Test-Daten fuer einen User."""
    today = date.today()
    for i in range(entries):
        db.add(TimeEntry(
            tenant_id=user.tenant_id, user_id=user.id,
            date=today - timedelta(days=i + 1),
            start_time=time(8, 0), end_time=time(16, 30), break_minutes=30,
        ))
    for i in range(absences):
        db.add(Absence(
            tenant_id=user.tenant_id, user_id=user.id,
            date=today - timedelta(days=10 + i),
            type=AbsenceType.VACATION, hours=8.0,
        ))
    for i in range(vacations):
        db.add(VacationRequest(
            tenant_id=user.tenant_id, user_id=user.id,
            date=today + timedelta(days=14 + i), hours=8.0,
            absence_type="vacation",
            status=VacationRequestStatus.PENDING.value,
            note=f"Antrag {i}",
        ))
    for i in range(change_requests):
        db.add(ChangeRequest(
            tenant_id=user.tenant_id, user_id=user.id,
            entry_kind="time_entry", change_type="update",
            proposed_date=today - timedelta(days=i),
            status="pending",
        ))
    db.commit()


# =============================================================================
# Happy path
# =============================================================================

class TestHappyPath:
    def test_returns_own_data(self, db, alice, alice_client):
        _make_data(db, alice, entries=3, absences=2, vacations=1)
        resp = alice_client.get("/api/me/data-export")
        assert resp.status_code == 200
        # JSON-Download mit attachment-Header
        assert resp.headers["content-type"].startswith("application/json")
        assert "attachment" in resp.headers["content-disposition"]
        assert "alice" in resp.headers["content-disposition"]

        body = json.loads(resp.content)
        assert body["export_type"] == "self_service_dsgvo_art15"
        assert body["subject"]["username"] == "alice"
        assert "password_hash" not in body["subject"]
        assert body["counts"]["time_entries"] == 3
        assert body["counts"]["absences"] == 2
        assert body["counts"]["vacation_requests"] == 1
        assert len(body["time_entries"]) == 3
        assert len(body["absences"]) == 2
        assert len(body["vacation_requests"]) == 1

    def test_time_entry_includes_arbzg_fields(self, db, alice, alice_client):
        # §10 ArbZG: sunday_exception_reason muss im Auskunfts-Export sein
        # (Pflichtbestandteil der Aufzeichnung). DSGVO Art. 15: note + created_at
        # gehoeren ebenfalls zur "Kopie der personenbezogenen Daten".
        _make_data(db, alice, entries=1, absences=0, vacations=0)
        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        te = body["time_entries"][0]
        assert "note" in te
        assert "sunday_exception_reason" in te
        assert "created_at" in te

    def test_empty_user_returns_empty_lists(self, db, alice, alice_client):
        resp = alice_client.get("/api/me/data-export")
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["counts"]["time_entries"] == 0
        assert body["counts"]["absences"] == 0
        assert body["counts"]["vacation_requests"] == 0
        assert body["counts"]["change_requests"] == 0
        assert body["subject"]["username"] == "alice"


# =============================================================================
# Isolation: own data only
# =============================================================================

class TestIsolation:
    def test_same_tenant_foreign_user_excluded(self, db, alice, bob, alice_client):
        # Alice exportiert. Bob ist im gleichen Tenant — seine Daten duerfen NICHT
        # in Alices Export landen.
        _make_data(db, alice, entries=1, absences=0, vacations=0)
        _make_data(db, bob, entries=5, absences=3, vacations=2)

        resp = alice_client.get("/api/me/data-export")
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["counts"]["time_entries"] == 1
        assert body["counts"]["absences"] == 0
        assert body["counts"]["vacation_requests"] == 0
        for te in body["time_entries"]:
            assert te["user_id"] == str(alice.id)
        # Subject ist Alice, nicht Bob
        assert body["subject"]["id"] == str(alice.id)

    def test_other_tenant_user_excluded(self, db, alice, carol_other_tenant, alice_client):
        # Carol ist in Tenant 2. Auch wenn Alice exportiert, dürfen Carols Daten
        # NIE im Export auftauchen — weder per RLS noch per Filter.
        _make_data(db, alice, entries=1, absences=0, vacations=0)
        _make_data(db, carol_other_tenant, entries=10, absences=5, vacations=3)

        resp = alice_client.get("/api/me/data-export")
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["counts"]["time_entries"] == 1
        # Alice-Daten, kein Carol-Bytes
        for te in body["time_entries"]:
            assert te["user_id"] == str(alice.id)


# =============================================================================
# Audit-Log
# =============================================================================

class TestAudit:
    def test_export_creates_audit_log(self, db, alice, alice_client):
        _make_data(db, alice, entries=2, vacations=1)
        # Vor dem Export: keine self_data_export-Eintraege
        pre = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "self_data_export",
            TimeEntryAuditLog.user_id == alice.id,
        ).count()
        assert pre == 0

        resp = alice_client.get("/api/me/data-export")
        assert resp.status_code == 200

        post = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "self_data_export",
            TimeEntryAuditLog.user_id == alice.id,
        ).all()
        assert len(post) == 1
        log = post[0]
        assert log.action == "self_data_export"
        assert log.changed_by == alice.id
        assert log.tenant_id == alice.tenant_id
        # Note enthaelt die Counts fuer Nachvollziehbarkeit
        assert "Zeiteintraege" in log.new_note
        assert "Urlaubsantraege" in log.new_note

    def test_source_marker_length_under_40(self):
        # Migration 037: time_entry_audit_logs.source ist varchar(40).
        # 'self_data_export' = 16 Zeichen — sicher unter dem Limit.
        assert len("self_data_export") < 40


# =============================================================================
# Audit-Logs werden mit-exportiert (DSGVO Art. 15 Pflicht: "Verarbeitete Daten")
# =============================================================================

class TestAuditLogInclusion:
    def test_own_audit_logs_included(self, db, alice, alice_client):
        # Lege manuelle Audit-Log-Rows fuer Alice an
        db.add(TimeEntryAuditLog(
            tenant_id=alice.tenant_id, user_id=alice.id, changed_by=alice.id,
            action="manual", source="manual", new_note="historisch",
        ))
        db.add(TimeEntryAuditLog(
            tenant_id=alice.tenant_id, user_id=alice.id, changed_by=alice.id,
            action="vacation_request_edit", source="vacation_request_edit",
            new_note="MA hat selbst editiert",
        ))
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        # Beide vorhandenen Audit-Rows muessen drin sein. Der self_data_export-
        # Eintrag fuer diesen Aufruf wird NACH dem Payload-Build geschrieben
        # und erscheint deshalb erst beim naechsten Export — das ist OK.
        assert body["counts"]["audit_logs"] == 2
        sources = {a["source"] for a in body["audit_logs"]}
        assert "vacation_request_edit" in sources
        assert "manual" in sources

    def test_foreign_user_audit_logs_excluded(self, db, alice, bob, alice_client):
        # Bobs Audit-Log darf nicht in Alices Export
        db.add(TimeEntryAuditLog(
            tenant_id=bob.tenant_id, user_id=bob.id, changed_by=bob.id,
            action="manual", source="manual", new_note="Bobs Aktion",
        ))
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        for a in body["audit_logs"]:
            # Entweder alice ist user_id (data subject) ODER alice changed_by (actor) —
            # Bobs Eintrag mit user_id=bob darf nicht enthalten sein.
            assert a["user_id"] == str(alice.id) or a["changed_by"] == str(alice.id)
            assert a["user_id"] != str(bob.id)
