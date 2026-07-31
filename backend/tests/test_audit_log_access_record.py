"""#431 / Art. 5(2) + Art. 9 DSGVO: das Zugriffsprotokoll fuer das
Aenderungsprotokoll selbst.

``GET /api/admin/audit-log`` zeigt seit #431 ``old_note``/``new_note`` an, und
die Rueckrechnung nach einer Wochenstunden-Aenderung schreibt dort deutschen
Klartext je nachgezogener Abwesenheit („Krank 8,0 h"). Damit sieht ein Admin
ueber diese Flaeche dieselben Gesundheitsdaten wie ueber die
Abwesenheitsliste, das Journal und die Berichte — die alle einen
Zugriffsvermerk schreiben. Diese eine tat es nicht.

Muster angelehnt an ``absences.list_absences`` (absences.py): nur bei einem
GEZIELTEN Zugriff auf eine FREMDE Person. ANDERS als das Vorbild wird hier
(Fix-Welle 4 #2) NUR geschrieben, wenn die Antwort tatsächlich sensible
Inhalte enthält (Marker ``health_data_read``, ``source="dsgvo"``) — sonst
liefe der Vermerk in dieselbe Tabelle ein, die dieser Endpoint auflistet
(Feedback-Loop). ``audit_log_read`` ist nur noch ein Bestandsmarker aus
Zeilen von vor diesem Fix.
"""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db, Base
from app.middleware.auth import require_admin
from app.models import TimeEntryAuditLog, User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _create_test_app() -> FastAPI:
    from app.routers import admin_time_entries
    app = FastAPI()
    app.include_router(admin_time_entries.router)
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


@pytest.fixture(scope="function")
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default",
               is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, role=UserRole.EMPLOYEE):
    u = User(username=username, email=f"{username}@x.de",
             password_hash=auth_service.hash_password("x"),
             first_name=username, last_name="T", role=role,
             weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
             is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "adm", role=UserRole.ADMIN)


@pytest.fixture
def emp(db, default_tenant):
    return _make_user(db, "emp")


def _client_as(db, user):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[require_admin] = lambda: user
    return TestClient(_app)


def _seed_row(db, user, admin, source="wh_change", **kw):
    row = TimeEntryAuditLog(
        time_entry_id=None, user_id=user.id, changed_by=admin.id,
        action="update", source=source, old_date=date(2026, 3, 2),
        new_date=date(2026, 3, 2), tenant_id=DEFAULT_TENANT_ID, **kw)
    db.add(row)
    db.commit()
    return row


def _access_records(db):
    return db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.source == "dsgvo").all()


def test_health_note_read_is_recorded(db, default_tenant, admin, emp):
    """Reproduktion: die Rueckrechnungs-Zeile traegt „Krank 8,0 h" im Klartext.
    Ein gezielter Admin-Zugriff darauf MUSS einen Vermerk hinterlassen."""
    _seed_row(db, emp, admin, old_note="Krank 8,0 h",
              new_note="Krank 4,0 h — Wochenstunden 40,0 → 20,0 ab 02.03.2026")

    r = _client_as(db, admin).get(f"/api/admin/audit-log?user_id={emp.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text

    records = _access_records(db)
    assert len(records) == 1
    rec = records[0]
    assert rec.action == "health_data_read"
    assert rec.user_id == emp.id
    assert rec.changed_by == admin.id
    assert rec.source == "dsgvo"
    assert rec.time_entry_id is None
    assert "Gesundheitsdaten" in rec.new_note


def test_machine_readable_absence_note_also_counts(db, default_tenant, admin, emp):
    """Das zweite Notiz-Format (``absence:<typ>:<h>h``) traegt denselben Typ."""
    _seed_row(db, emp, admin, old_note="absence:sick:8.0h", source="vacation_refund")

    r = _client_as(db, admin).get(f"/api/admin/audit-log?user_id={emp.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text

    assert [x.action for x in _access_records(db)] == ["health_data_read"]


def test_non_sensitive_read_records_no_marker(db, default_tenant, admin, emp):
    """Urlaub ist kein Gesundheitsdatum. ANDERS als absences.py (Vorbild) wird
    hier KEIN Vermerk geschrieben: die Zeile liefe in dieselbe Tabelle ein,
    die dieser Endpoint selbst auflistet (Feedback-Loop, Fix-Welle 4 #2) —
    ohne sensiblen Inhalt in der Antwort besteht kein Art.-5(2)-Nachweisbedarf."""
    _seed_row(db, emp, admin, old_note="Urlaub 8,0 h", new_note="Urlaub 4,0 h — x")

    r = _client_as(db, admin).get(f"/api/admin/audit-log?user_id={emp.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text

    assert _access_records(db) == []


def test_empty_result_is_not_recorded(db, default_tenant, admin, emp):
    """ANDERS als absences.py: eine gezielte Suche, die (noch) nichts findet,
    enthaelt keine sensiblen Inhalte in der Antwort -> kein Vermerk (sonst
    Feedback-Loop in die eigene Liste, Fix-Welle 4 #2)."""
    r = _client_as(db, admin).get(f"/api/admin/audit-log?user_id={emp.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert _access_records(db) == []


def test_own_log_is_not_recorded(db, default_tenant, admin):
    """Der Blick ins eigene Protokoll ist kein Fremdzugriff."""
    _seed_row(db, admin, admin, old_note="Krank 8,0 h")

    r = _client_as(db, admin).get(f"/api/admin/audit-log?user_id={admin.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert _access_records(db) == []


def test_unfiltered_list_is_not_recorded(db, default_tenant, admin, emp):
    """Nur der GEZIELTE Zugriff auf EINE Person wird vermerkt — die
    ungefilterte Gesamtliste ist die Verwaltungsansicht (identisch zu
    absences.list_absences, das ebenfalls auf ``user_id`` gated)."""
    _seed_row(db, emp, admin, old_note="Krank 8,0 h")

    r = _client_as(db, admin).get("/api/admin/audit-log")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert _access_records(db) == []


def test_access_record_is_not_returned_as_a_change(db, default_tenant, admin, emp):
    """#284: der Vermerk darf die Aenderungsliste nicht verschmutzen —
    ``changes_only`` filtert ihn heraus."""
    _seed_row(db, emp, admin, old_note="Krank 8,0 h")
    client = _client_as(db, admin)
    client.get(f"/api/admin/audit-log?user_id={emp.id}")
    r = client.get(f"/api/admin/audit-log?user_id={emp.id}&changes_only=true")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert all(row["action"] in ("create", "update", "delete") for row in r.json())


def test_access_record_has_row_hash(db, default_tenant, admin, emp):
    """#121: der Vermerk muss durch den ``before_insert``-Hook laufen (kein
    Bulk-Insert) — sonst fehlt der Tamper-Evidence-Hash."""
    _seed_row(db, emp, admin, old_note="Krank 8,0 h")

    r = _client_as(db, admin).get(f"/api/admin/audit-log?user_id={emp.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text

    rec = _access_records(db)[0]
    assert rec.row_hash, "Zugriffsvermerk ohne row_hash — Bulk-Insert?"


def test_markers_fit_the_varchar_40_limit():
    """``action`` und ``source`` sind ``varchar(40)`` (Migrationen 037/044) —
    SQLite ignoriert das, Postgres wirft 500 (StringDataRightTruncation)."""
    from app.routers.admin_time_entries import _AUDIT_READ_ACTIONS
    for marker in _AUDIT_READ_ACTIONS:
        assert len(marker) <= 40
    assert len("dsgvo") <= 40
