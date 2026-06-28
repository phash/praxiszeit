"""Regressionstests für die Runde-2-Findings des UC-Reviews.

- AC-11 (vollständig): auch die Direkt-Buchung (create_absence) schließt
  'free'-Sondertage (24./31.12.) aus — nicht nur Betriebsferien/Urlaubsantrag.
- ADM-12 (Keyset-Tiebreaker): das Änderungsprotokoll paginiert über (created_at, id)
  und überspringt KEINE Zeilen, wenn mehrere Rows denselben created_at tragen
  (func.now() = Transaktionszeit bei Bulk-Inserts).
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, User, UserRole
from app.models.system_setting import SystemSetting
from app.models.time_entry_audit_log import TimeEntryAuditLog
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID


def _app() -> FastAPI:
    from app.routers import absences, admin_time_entries
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    app.include_router(admin_time_entries.router)
    return app


_APP = _app()


@pytest.fixture(autouse=True)
def _clear():
    yield
    _APP.dependency_overrides.clear()


def _client(db, current):
    def odb():
        yield db
    _APP.dependency_overrides[get_db] = odb
    _APP.dependency_overrides[get_current_user] = lambda: current
    _APP.dependency_overrides[require_admin] = lambda: current
    return TestClient(_APP)


def _mk_employee(db) -> User:
    u = User(
        id=uuid.uuid4(), username=f"u_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@t.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Erika", last_name="Muster", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_direct_vacation_booking_skips_free_special_day(db):
    """AC-11: Direkt gebuchter Urlaub über den 24.12. (free) legt am 24.12. KEINE
    Abwesenheit an — der soll-freie Tag kostet keinen Urlaubstag."""
    emp = _mk_employee(db)
    db.add(SystemSetting(key="special_day_dec24_mode", tenant_id=DEFAULT_TENANT_ID, value="free"))
    db.commit()
    resp = _client(db, emp).post("/api/absences", json={
        "date": "2025-12-22", "end_date": "2025-12-26", "type": "vacation", "hours": 8,
    })
    assert resp.status_code == 201, resp.text
    booked = {a.date for a in db.query(Absence).filter(Absence.user_id == emp.id).all()}
    assert date(2025, 12, 24) not in booked, "24.12. (free) darf NICHT gebucht werden"
    assert date(2025, 12, 22) in booked and date(2025, 12, 26) in booked


def test_audit_pagination_keeps_rows_with_equal_created_at(db, test_admin):
    """ADM-12: 5 Audit-Rows mit IDENTISCHEM created_at (wie ein Bulk-Insert). Über
    zwei Seiten (limit 3 + Komposit-Cursor) müssen alle 5 erreichbar sein — der
    Tiebreaker (created_at, id) verhindert das Verschlucken an der Seitengrenze."""
    emp = _mk_employee(db)
    ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    ids = []
    for _ in range(5):
        row = TimeEntryAuditLog(
            id=uuid.uuid4(), tenant_id=DEFAULT_TENANT_ID, user_id=emp.id,
            changed_by=test_admin.id, action="create", source="manual", created_at=ts,
        )
        db.add(row)
        ids.append(str(row.id))
    db.commit()
    client = _client(db, test_admin)
    p1 = client.get(f"/api/admin/audit-log?user_id={emp.id}&limit=3").json()
    assert len(p1) == 3, p1
    last = p1[-1]
    p2 = client.get(
        f"/api/admin/audit-log?user_id={emp.id}&limit=3"
        f"&before={last['created_at']}&before_id={last['id']}"
    ).json()
    seen = {r["id"] for r in p1} | {r["id"] for r in p2}
    assert set(ids).issubset(seen), (len(seen), sorted(ids))
