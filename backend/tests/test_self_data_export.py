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

    def test_art15_meta_block_present(self, db, alice, alice_client):
        # DSGVO Art. 15 (1)(a-h): Pflichtangaben zur Verarbeitung muessen
        # zusaetzlich zur Datenkopie (Abs. 3) geliefert werden.
        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        meta = body["art15_meta"]
        for key in ("a_zwecke", "b_datenkategorien", "c_empfaenger",
                    "d_speicherdauer", "e_rechte", "f_beschwerderecht",
                    "g_quelle", "h_automatisierte_entscheidung"):
            assert key in meta, f"art15_meta fehlt {key}"
        # Datenkategorien als Liste
        assert isinstance(meta["b_datenkategorien"], list)
        assert len(meta["b_datenkategorien"]) >= 5
        # Rechte als Dict mit den Pflicht-Eintraegen
        for r in ("berichtigung", "loeschung", "einschraenkung",
                  "widerspruch", "datenportabilitaet"):
            assert r in meta["e_rechte"], f"art15_meta.e_rechte fehlt {r}"

    def test_subject_includes_arbzg_status_fields(self, db, alice, alice_client):
        # § 6 ArbZG (Nachtarbeiter) und § 18 ArbZG (leitende Angestellte)
        # sind Pflichtbestandteile der Auskunft, plus profile_picture (Foto).
        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        s = body["subject"]
        for f in ("is_night_worker", "exempt_from_arbzg", "profile_picture",
                  "vacation_days", "work_days_per_week", "calendar_color",
                  "created_at", "totp_enabled"):
            assert f in s, f"subject fehlt {f}"
        # Sicherheits-relevante Felder MUESSEN ausgeschlossen sein
        assert "password_hash" not in s
        assert "totp_secret" not in s
        assert "last_totp_counter" not in s

    def test_change_request_export_has_substance(self, db, alice, alice_client):
        # DSGVO Art. 15: Begruendung des MA + vorgeschlagene + originale Werte
        # gehoeren in den Export, nicht nur id/status.
        from datetime import time as dt_time
        cr = ChangeRequest(
            tenant_id=alice.tenant_id, user_id=alice.id,
            request_type="update", entry_kind="time_entry",
            reason="Ich hatte vergessen einzustempeln",
            proposed_date=date.today(), proposed_start_time=dt_time(8, 0),
            proposed_end_time=dt_time(16, 30), proposed_break_minutes=30,
            proposed_note="nachgetragen",
            original_date=date.today(), original_start_time=dt_time(9, 0),
            original_end_time=dt_time(16, 30), original_break_minutes=30,
            original_note="alt",
            status="pending",
        )
        db.add(cr)
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        assert len(body["change_requests"]) == 1
        c = body["change_requests"][0]
        # MA-Eigentext muss da sein
        assert c["reason"] == "Ich hatte vergessen einzustempeln"
        # Vorgeschlagene Werte
        assert c["proposed_start_time"] == "08:00:00"
        assert c["proposed_note"] == "nachgetragen"
        # Original-Werte
        assert c["original_start_time"] == "09:00:00"
        assert c["original_note"] == "alt"

    def test_audit_log_export_has_old_new_substance(self, db, alice, alice_client):
        # DSGVO Art. 15: Aenderungshistorie muss inhaltlich nachvollziehbar sein.
        # Ohne old_*/new_* sieht der MA nur "es gab eine Aenderung" — Substanz fehlt.
        from datetime import time as dt_time
        db.add(TimeEntryAuditLog(
            tenant_id=alice.tenant_id, user_id=alice.id, changed_by=alice.id,
            action="update", source="manual",
            old_date=date.today(), old_start_time=dt_time(8, 0),
            old_end_time=dt_time(16, 0), old_break_minutes=30, old_note="vorher",
            new_date=date.today(), new_start_time=dt_time(8, 30),
            new_end_time=dt_time(16, 30), new_break_minutes=45, new_note="nachher",
        ))
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        # Mind. 1 mit substantiellen old/new-Werten
        substantial = [a for a in body["audit_logs"]
                       if a.get("old_start_time") and a.get("new_start_time")]
        assert len(substantial) >= 1
        log = substantial[0]
        assert log["old_start_time"] == "08:00:00"
        assert log["new_start_time"] == "08:30:00"
        assert log["old_note"] == "vorher"
        assert log["new_note"] == "nachher"
        assert log["old_break_minutes"] == 30
        assert log["new_break_minutes"] == 45

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


# =============================================================================
# user_directory: Reviewer-UUIDs -> Klartext-Namen (Issue #128)
# =============================================================================

class TestUserDirectory:
    """DSGVO Art. 12 Abs. 1 'in verstaendlicher Form' + Art. 15 (1)(c):
    Reviewer-/Editor-UUIDs muessen mit Klartext-Namen aufloesbar sein."""

    def test_user_directory_present_when_empty(self, db, alice, alice_client):
        # Auch ohne Reviewer-Daten muss der Schluessel existieren (stabiles Schema).
        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        assert "user_directory" in body
        assert isinstance(body["user_directory"], dict)
        assert body["user_directory"] == {}

    def test_vacation_request_reviewer_resolved(self, db, alice, alice_client):
        # Admin im gleichen Tenant approved Alices Urlaub.
        # WICHTIG: Lokale Variablen vor _user() merken — _user() committed,
        # dadurch expired alice.tenant_id und SQLAlchemy versucht reload.
        alice_id = alice.id
        alice_tid = alice.tenant_id
        admin = _user(db, "admin", role=UserRole.ADMIN)
        admin_id = admin.id
        from datetime import datetime as dt, timezone as tz
        vr = VacationRequest(
            tenant_id=alice_tid, user_id=alice_id,
            date=date.today() + timedelta(days=7), hours=8.0,
            absence_type="vacation", status=VacationRequestStatus.APPROVED.value,
            reviewed_by=admin_id, reviewed_at=dt.now(tz.utc),
        )
        db.add(vr)
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        assert body["vacation_requests"][0]["reviewed_by"] == str(admin_id)
        assert str(admin_id) in body["user_directory"]
        assert body["user_directory"][str(admin_id)] == "Admin Test"

    def test_vacation_request_last_modified_by_resolved(self, db, alice, alice_client):
        alice_id = alice.id
        alice_tid = alice.tenant_id
        editor = _user(db, "editor", role=UserRole.ADMIN)
        editor_id = editor.id
        vr = VacationRequest(
            tenant_id=alice_tid, user_id=alice_id,
            date=date.today() + timedelta(days=10), hours=8.0,
            absence_type="vacation", status=VacationRequestStatus.PENDING.value,
            last_modified_by=editor_id,
        )
        db.add(vr)
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        assert body["vacation_requests"][0]["last_modified_by"] == str(editor_id)
        assert body["user_directory"][str(editor_id)] == "Editor Test"

    def test_change_request_reviewer_resolved(self, db, alice, alice_client):
        alice_id = alice.id
        alice_tid = alice.tenant_id
        reviewer = _user(db, "reviewer", role=UserRole.ADMIN)
        reviewer_id = reviewer.id
        from datetime import datetime as dt, timezone as tz
        cr = ChangeRequest(
            tenant_id=alice_tid, user_id=alice_id,
            request_type="update", entry_kind="time_entry",
            reason="Korrektur noetig",
            proposed_date=date.today(), status="approved",
            reviewed_by=reviewer_id, reviewed_at=dt.now(tz.utc),
        )
        db.add(cr)
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        assert body["change_requests"][0]["reviewed_by"] == str(reviewer_id)
        assert body["user_directory"][str(reviewer_id)] == "Reviewer Test"

    def test_audit_log_changed_by_resolved(self, db, alice, alice_client):
        alice_id = alice.id
        alice_tid = alice.tenant_id
        auditor = _user(db, "auditor", role=UserRole.ADMIN)
        auditor_id = auditor.id
        db.add(TimeEntryAuditLog(
            tenant_id=alice_tid, user_id=alice_id, changed_by=auditor_id,
            action="update", source="manual", new_note="Admin hat fuer MA korrigiert",
        ))
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        assert any(a["changed_by"] == str(auditor_id) for a in body["audit_logs"])
        assert body["user_directory"][str(auditor_id)] == "Auditor Test"

    def test_cross_tenant_reviewer_not_resolved(
        self, db, alice, carol_other_tenant, alice_client
    ):
        # F-026: Reviewer-UUID aus FREMDEM Tenant darf nicht aufgeloest werden.
        # carol_other_tenant lebt in SECOND_TENANT_ID; ihre UUID darf zwar in
        # Alices Daten auftauchen (durch was auch immer), aber das directory
        # darf sie NICHT aufloesen — Cross-Tenant-Schutz.
        alice_id = alice.id
        alice_tid = alice.tenant_id
        carol_id = carol_other_tenant.id
        db.add(TimeEntryAuditLog(
            tenant_id=alice_tid, user_id=alice_id, changed_by=carol_id,
            action="manual", source="manual", new_note="cross-tenant test",
        ))
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        assert any(a["changed_by"] == str(carol_id) for a in body["audit_logs"])
        assert str(carol_id) not in body["user_directory"]

    def test_multiple_reviewers_all_resolved_one_query(self, db, alice, alice_client):
        # Performance: max. 1 Extra-Query, egal wieviele Reviewer.
        # Wir verifizieren das funktionale Ergebnis (alle Namen aufgeloest).
        alice_id = alice.id
        alice_tid = alice.tenant_id
        rev_ids = []
        for name in ("rev1", "rev2", "rev3"):
            r = _user(db, name, role=UserRole.ADMIN)
            rev_ids.append((r.id, name.title()))
        from datetime import datetime as dt, timezone as tz
        for i, (rid, _) in enumerate(rev_ids):
            db.add(VacationRequest(
                tenant_id=alice_tid, user_id=alice_id,
                date=date.today() + timedelta(days=20 + i), hours=8.0,
                absence_type="vacation", status=VacationRequestStatus.APPROVED.value,
                reviewed_by=rid, reviewed_at=dt.now(tz.utc),
            ))
        db.commit()

        resp = alice_client.get("/api/me/data-export")
        body = json.loads(resp.content)
        for rid, name in rev_ids:
            assert str(rid) in body["user_directory"]
            assert body["user_directory"][str(rid)] == f"{name} Test"
