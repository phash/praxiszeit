"""§16-ArbZG Superadmin-Export — Audit-Marker-Korrektheit (Review 2026-05-29, H1).

Der Export-Endpoint schreibt einen Audit-Marker mit
``action="arbzg_superadmin_export"`` (23 Zeichen). Die ``action``-Spalte war
``varchar(20)`` → auf PostgreSQL ``StringDataRightTruncation`` → 500 beim
gesetzlich vorgeschriebenen Notfall-Export deaktivierter Tenants. Die
SQLite-Test-Suite ignoriert varchar-Längen, daher prüfen wir den
Modell-Vertrag direkt (Compile-Zeit-Garantie) sowie die Defensiv-Eigenschaft,
dass ein fehlgeschlagener Audit-Write den Export NICHT abbricht.
"""
from __future__ import annotations

import uuid

import pytest

from app.models import TimeEntryAuditLog, User, UserRole
from app.services import auth_service


# ---------------------------------------------------------------------------
# Modell-Vertrag: action-Spalte muss alle verwendeten Marker fassen
# ---------------------------------------------------------------------------

# Alle action-Marker, die irgendwo im Code geschrieben werden. Der längste
# (license_readonly_mode_entered = 29) bestimmt die Mindestbreite der Spalte.
KNOWN_ACTION_MARKERS = [
    "create",
    "update",
    "delete",
    "auto_close",
    "arbzg_superadmin_export",        # superadmin.py
    "license_readonly_mode_entered",  # main.py
]


class TestActionColumnLength:
    def test_action_column_holds_all_markers(self):
        """time_entry_audit_logs.action muss jeden verwendeten Marker fassen.
        varchar(20) sprengte 'arbzg_superadmin_export' (23) und
        'license_readonly_mode_entered' (29) → 500 auf Postgres."""
        col_len = TimeEntryAuditLog.__table__.c.action.type.length
        longest = max(len(m) for m in KNOWN_ACTION_MARKERS)
        assert col_len is not None and col_len >= longest, (
            f"action-Spalte ist varchar({col_len}), längster Marker ist "
            f"{longest} Zeichen → StringDataRightTruncation auf Postgres"
        )

    def test_action_column_has_headroom_like_source(self):
        """Analog zu source (Migration 037) soll action auf 40 stehen —
        Headroom für künftige Marker ohne weitere Migration."""
        assert TimeEntryAuditLog.__table__.c.action.type.length >= 40


# ---------------------------------------------------------------------------
# Defensiv: Audit-Write-Fehler darf den §16-Export nicht abbrechen
# ---------------------------------------------------------------------------

@pytest.fixture
def superadmin_user(db):
    """Superadmin = User ohne tenant_id."""
    sa = User(
        username="superadmin",
        email="super@example.com",
        password_hash=auth_service.hash_password("superpass1234"),
        first_name="Super",
        last_name="Admin",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        is_active=True,
        track_hours=False,
        tenant_id=None,
    )
    db.add(sa)
    db.commit()
    db.refresh(sa)
    return sa


class TestExportSurvivesAuditFailure:
    def test_export_returns_even_if_audit_commit_fails(
        self, db, default_tenant, superadmin_user, monkeypatch
    ):
        """Schlägt der Audit-Marker-Write fehl, muss der gesetzlich
        vorgeschriebene Export trotzdem ausgeliefert werden (nicht 500)."""
        from app.routers import superadmin as sa_router
        from app.core.limiter import limiter
        from starlette.responses import StreamingResponse

        # SQLite kennt kein RLS → set_superadmin_context no-oppen.
        monkeypatch.setattr(sa_router, "set_superadmin_context", lambda _db: None)
        # L-6: der Endpoint trägt jetzt @limiter.limit (+ request-Param). Beim
        # Direkt-Aufruf (kein App-Kontext) den Limiter durchreichen.
        monkeypatch.setattr(limiter, "enabled", False)

        # commit() so patchen, dass der Audit-Marker-Write hart fehlschlägt.
        original_commit = db.commit

        def boom():
            raise RuntimeError("simulated audit-write failure")

        monkeypatch.setattr(db, "commit", boom)

        response = sa_router.export_tenant_arbzg_data(
            request=None,  # nur für den @limiter.limit-Decorator; der Body nutzt es nicht
            tenant_id=default_tenant.id,
            db=db,
            current_user=superadmin_user,
        )

        assert isinstance(response, StreamingResponse)
        # Aufräumen: echtes commit wiederherstellen für Fixture-Teardown.
        monkeypatch.setattr(db, "commit", original_commit)
