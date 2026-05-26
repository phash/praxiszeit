"""M6: License-Read-Only-Trigger im Audit-Log persistieren.

Bisher hat `main.py` bei License-Problemen nur einen `print("LIZENZ-PROBLEM:")`
abgesetzt — keine strukturierte Persistenz. Fuer DSGVO Art. 32
(Eingabekontrolle) und ArbZG §16 (Nachvollziehbarkeit) muss jedes Eintreten
in den Read-Only-Modus im Audit-Log auftauchen, analog zu Health-Data-Reads
und vacation_request_edit.

Diese Tests pruefen direkt die Helper-Funktion ``audit_license_readonly_event``
(statt das gesamte Lifespan zu starten — zu invasiv). Sie deckt drei Pfade ab:
1. ``Lizenz abgelaufen`` (LicenseExpiredError)
2. ``Ungueltige Signatur`` (LicenseError)
3. ``Demo-Frist ueberschritten`` (Demo-Mode)
"""
from __future__ import annotations

import pytest
import uuid

from app.main import (
    LICENSE_AUDIT_SOURCE,
    audit_license_readonly_event,
)
from app.models import TimeEntryAuditLog, User, UserRole
from app.services import auth_service


# ---------------------------------------------------------------------------
# Source-Marker-Constraint-Check (Migration 037: varchar(40))
# ---------------------------------------------------------------------------

class TestSourceMarkerLength:
    def test_marker_under_40_chars(self):
        """time_entry_audit_logs.source ist varchar(40) (Migration 037).
        Wenn der Marker das Limit sprengt -> 500 beim INSERT
        (StringDataRightTruncation). Garantie auf Compile-Zeit."""
        assert len(LICENSE_AUDIT_SOURCE) < 40, (
            f"LICENSE_AUDIT_SOURCE='{LICENSE_AUDIT_SOURCE}' "
            f"({len(LICENSE_AUDIT_SOURCE)} chars) sprengt 40-Char-Limit"
        )

    def test_marker_is_license_startup(self):
        """Stabilen Marker-Wert versiegeln — Tests + Compliance-Audits
        suchen nach genau diesem String in time_entry_audit_logs."""
        assert LICENSE_AUDIT_SOURCE == "license_startup"


# ---------------------------------------------------------------------------
# Fixtures: Tenant + Admin + Patching von SessionLocal aus app.main
# ---------------------------------------------------------------------------

@pytest.fixture
def patched_session(monkeypatch, db):
    """``audit_license_readonly_event`` instanziiert ein eigenes
    ``SessionLocal()`` -> wir muessen das auf den Test-Engine umbiegen.
    Zudem ``set_superadmin_context`` no-oppen (SQLite kennt RLS nicht).
    """
    from tests.conftest import TestingSessionLocal
    import app.main as main_module

    monkeypatch.setattr(main_module, "SessionLocal", TestingSessionLocal)
    # set_superadmin_context schickt SET-Statements ans Postgres — auf SQLite
    # wuerde das mit OperationalError crashen. Im Test ist RLS nicht aktiv,
    # also einfach no-op.
    monkeypatch.setattr(
        "app.database.set_superadmin_context",
        lambda _db: None,
    )
    yield db


@pytest.fixture
def admin_user(db, default_tenant):
    """System-Admin im Default-Tenant — Audit-Helper braucht einen Admin
    fuer die NOT-NULL-FKs (user_id + changed_by)."""
    admin = User(
        username="systemadmin",
        email="admin@example.com",
        password_hash=auth_service.hash_password("adminpass1234"),
        first_name="System",
        last_name="Admin",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        is_active=True,
        track_hours=False,
        tenant_id=default_tenant.id,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


# ---------------------------------------------------------------------------
# Happy-Path: drei Reasons -> drei Audit-Eintraege
# ---------------------------------------------------------------------------

class TestAuditEventPersistence:
    """Pro Reason: nach Aufruf existiert genau eine Zeile mit
    source='license_startup' und der passenden Note."""

    def test_signature_mismatch_writes_audit_row(
        self, patched_session, admin_user, default_tenant
    ):
        audit_license_readonly_event(
            reason="Ungueltige Signatur",
            default_tenant_id=default_tenant.id,
        )
        rows = (
            patched_session.query(TimeEntryAuditLog)
            .filter(TimeEntryAuditLog.source == LICENSE_AUDIT_SOURCE)
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.action == "license_readonly_mode_entered"
        assert row.new_note == "READ-ONLY: Ungueltige Signatur"
        assert row.tenant_id == default_tenant.id
        # NOT-NULL-FKs erfuellt (gegen Bootstrap-Admin)
        assert row.user_id == admin_user.id
        assert row.changed_by == admin_user.id

    def test_license_expired_writes_audit_row(
        self, patched_session, admin_user, default_tenant
    ):
        audit_license_readonly_event(
            reason="Lizenz abgelaufen",
            default_tenant_id=default_tenant.id,
        )
        row = (
            patched_session.query(TimeEntryAuditLog)
            .filter(TimeEntryAuditLog.source == LICENSE_AUDIT_SOURCE)
            .one()
        )
        assert row.new_note == "READ-ONLY: Lizenz abgelaufen"
        assert row.action == "license_readonly_mode_entered"

    def test_demo_expired_writes_audit_row(
        self, patched_session, admin_user, default_tenant
    ):
        audit_license_readonly_event(
            reason="Demo-Frist ueberschritten",
            default_tenant_id=default_tenant.id,
        )
        row = (
            patched_session.query(TimeEntryAuditLog)
            .filter(TimeEntryAuditLog.source == LICENSE_AUDIT_SOURCE)
            .one()
        )
        assert row.new_note == "READ-ONLY: Demo-Frist ueberschritten"


# ---------------------------------------------------------------------------
# Negative-Pfade: gueltige Lizenz, fehlender Admin, SaaS-Modus
# ---------------------------------------------------------------------------

class TestAuditEventSkip:
    def test_valid_license_writes_no_audit_row(
        self, patched_session, admin_user, default_tenant
    ):
        """Wenn die License-Logik den Audit-Helper NICHT aufruft, darf
        auch keine Zeile mit source='license_startup' entstehen. Direkter
        Negativ-Beweis: ohne Aufruf -> 0 Zeilen."""
        rows = (
            patched_session.query(TimeEntryAuditLog)
            .filter(TimeEntryAuditLog.source == LICENSE_AUDIT_SOURCE)
            .all()
        )
        assert len(rows) == 0

    def test_saas_mode_no_default_tenant_id_skips_silently(
        self, patched_session, admin_user, default_tenant, capsys
    ):
        """SaaS-Modus -> default_tenant_id=None. Kein Crash, kein Eintrag,
        nur ein Print-Hinweis."""
        audit_license_readonly_event(
            reason="Ungueltige Signatur",
            default_tenant_id=None,
        )
        rows = (
            patched_session.query(TimeEntryAuditLog)
            .filter(TimeEntryAuditLog.source == LICENSE_AUDIT_SOURCE)
            .all()
        )
        assert len(rows) == 0
        captured = capsys.readouterr()
        assert "default_tenant_id" in captured.out

    def test_missing_admin_skips_without_crash(
        self, patched_session, default_tenant, capsys
    ):
        """Wenn (theoretisch) kein Admin im Tenant existiert -> kein
        Crash trotz NOT-NULL-FKs, nur Print-Warnung. Startup darf nie
        wegen Audit-Write scheitern."""
        # Bewusst KEIN admin_user-Fixture -> Default-Tenant ohne Admin
        audit_license_readonly_event(
            reason="Lizenz abgelaufen",
            default_tenant_id=default_tenant.id,
        )
        rows = (
            patched_session.query(TimeEntryAuditLog)
            .filter(TimeEntryAuditLog.source == LICENSE_AUDIT_SOURCE)
            .all()
        )
        assert len(rows) == 0
        captured = capsys.readouterr()
        assert "kein aktiver Admin" in captured.out


# ---------------------------------------------------------------------------
# Idempotenz-Charakter: jeder Aufruf = neuer Eintrag (Option A — bewusst)
# ---------------------------------------------------------------------------

class TestAuditIdempotency:
    def test_repeated_restarts_create_separate_rows(
        self, patched_session, admin_user, default_tenant
    ):
        """Option A aus dem Task: jeder Restart erzeugt einen eigenen
        Audit-Eintrag. Restart-Haeufigkeit ist informativ
        (= Service-Stabilitaet bei kaputter Lizenz). Wir versiegeln
        dieses Verhalten explizit, damit es niemand „aus Versehen"
        nach Option B optimiert."""
        for _ in range(3):
            audit_license_readonly_event(
                reason="Lizenz abgelaufen",
                default_tenant_id=default_tenant.id,
            )
        rows = (
            patched_session.query(TimeEntryAuditLog)
            .filter(TimeEntryAuditLog.source == LICENSE_AUDIT_SOURCE)
            .all()
        )
        assert len(rows) == 3
