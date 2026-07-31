"""Year-closing guards & carryover provenance.

Fix #4: create_year_closing must refuse (409) while a PENDING VacationRequest
        overlaps the closing year (approving it later would move the frozen
        balance), mirroring the existing PENDING ChangeRequest guard.
Fix #5: idempotent year closing (no duplicate carryover) + a non-destructive
        ``warning`` on retroactive changes to an already-closed year.
Fix #7: ``YearCarryover.source`` distinguishes year-closing rows from manual
        ones, so delete_year_closing only removes the former.
"""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db, Base
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType, YearCarryover
from app.models.change_request import (
    ChangeRequest, ChangeRequestStatus, ChangeRequestType,
)
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.services import auth_service, calculation_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _create_test_app() -> FastAPI:
    from app.routers import admin_carryovers, vacation_requests, admin_vacations, company_closures
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(admin_carryovers.router)
    app.include_router(vacation_requests.router)
    app.include_router(admin_vacations.router)
    app.include_router(company_closures.router)
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
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30):
    u = User(
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("x"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "adm1", role=UserRole.ADMIN)


@pytest.fixture
def emp(db, default_tenant):
    return _make_user(db, "emp1")


def _client_as(db, user):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: user
    _app.dependency_overrides[require_admin] = lambda: user
    return TestClient(_app)


def _set_toggle(db, on: bool):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


# --- Fix #4: PENDING VacationRequest guard ------------------------------------


def test_year_closing_blocked_by_pending_vacation_request(db, default_tenant, admin, emp):
    db.add(VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 7, 1),
        end_date=date(2025, 7, 5), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.PENDING.value))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 409, r.text
    assert "Urlaubsantr" in r.json()["detail"]


def test_year_closing_allows_pending_request_in_other_year(db, default_tenant, admin, emp):
    db.add(VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 7, 1),
        end_date=date(2026, 7, 5), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.PENDING.value))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text


def test_year_closing_ignores_non_pending_request(db, default_tenant, admin, emp):
    db.add(VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 7, 1),
        end_date=date(2025, 7, 5), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.APPROVED.value))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text


# --- Audit 2026-07-31 (A1): PENDING-ChangeRequest-Sperre über BEIDE Datumsspalten ---
#
# Die F-029-Sperre filterte nur über ``proposed_date``. Ein Lösch-Antrag trägt
# dort NULL — sein Tagesbezug steht ausschließlich in ``original_date`` — und
# wurde deshalb still nicht mitgezählt: der Jahresabschluss lief durch, und eine
# spätere Genehmigung löschte den Zeiteintrag, während der eingefrorene Übertrag
# falsch stehen blieb. Dasselbe galt für Anträge, die einen Eintrag AUS dem
# Abschlussjahr herausschieben (original_date im Jahr, proposed_date danach).


def _pending_cr(emp, **kw):
    return ChangeRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
        status=ChangeRequestStatus.PENDING,
        entry_kind="time_entry", reason="Audit-Test",
        **kw,
    )


def test_year_closing_blocked_by_pending_delete_change_request(db, default_tenant, admin, emp):
    """Lösch-Antrag: proposed_date IS NULL, Tagesbezug nur in original_date."""
    db.add(_pending_cr(
        emp, request_type=ChangeRequestType.DELETE,
        proposed_date=None, original_date=date(2025, 7, 1),
    ))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 409, r.text
    assert "Änderungsanträge" in r.json()["detail"]


def test_year_closing_blocked_by_cr_moving_entry_out_of_year(db, default_tenant, admin, emp):
    """Verschiebe-Antrag AUS dem Abschlussjahr heraus: nur original_date liegt drin."""
    db.add(_pending_cr(
        emp, request_type=ChangeRequestType.UPDATE,
        original_date=date(2025, 12, 30), proposed_date=date(2026, 1, 5),
    ))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 409, r.text
    assert "Änderungsanträge" in r.json()["detail"]


def test_year_closing_still_blocked_by_pending_create_change_request(db, default_tenant, admin, emp):
    """Kontrolle: der bisher schon erfasste Fall (proposed_date im Jahr) bleibt 409."""
    db.add(_pending_cr(
        emp, request_type=ChangeRequestType.CREATE,
        proposed_date=date(2025, 3, 4), original_date=None,
    ))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 409, r.text


def test_year_closing_allows_pending_change_request_in_other_year(db, default_tenant, admin, emp):
    """Kontrolle: liegen BEIDE Daten außerhalb, blockiert nichts (kein Over-Blocking)."""
    db.add(_pending_cr(
        emp, request_type=ChangeRequestType.UPDATE,
        original_date=date(2026, 5, 4), proposed_date=date(2026, 5, 5),
    ))
    db.add(_pending_cr(
        emp, request_type=ChangeRequestType.DELETE,
        original_date=date(2024, 5, 4), proposed_date=None,
    ))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text


def test_year_closing_ignores_non_pending_delete_change_request(db, default_tenant, admin, emp):
    """Kontrolle: ein bereits bearbeiteter Lösch-Antrag blockiert nicht."""
    cr = _pending_cr(
        emp, request_type=ChangeRequestType.DELETE,
        proposed_date=None, original_date=date(2025, 7, 1),
    )
    cr.status = ChangeRequestStatus.APPROVED
    db.add(cr)
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text


# --- Fix #5: idempotency + stale-closing warning ------------------------------


def test_double_year_closing_is_idempotent(db, default_tenant, admin, emp):
    client = _client_as(db, admin)
    r1 = client.post("/api/admin/year-closing/2025")
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/admin/year-closing/2025")
    assert r2.status_code == 200, r2.text
    _app.dependency_overrides.clear()
    # Exactly one carryover per active user for 2026 (no duplicate rows).
    rows = db.query(YearCarryover).filter(YearCarryover.year == 2026).all()
    assert len(rows) == 2  # admin + emp
    per_user = {r.user_id for r in rows}
    assert len(per_user) == 2


def test_cancel_vacation_after_closing_returns_stale_warning(db, default_tenant, admin, emp):
    # Close a FUTURE year so the approved vacation is still cancellable.
    calculation_service.create_year_closing(db, 2027, [emp])  # → carryover 2028
    vr = VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2027, 3, 2),
        end_date=date(2027, 3, 3), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.APPROVED.value)
    db.add(vr)
    db.add(Absence(user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2027, 3, 2),
                   type=AbsenceType.VACATION, hours=8.0, half_day=False))
    db.commit()
    db.refresh(vr)

    r = _client_as(db, emp).delete(f"/api/vacation-requests/{vr.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert "Jahresabschluss 2027" in r.json()["warning"]


def test_cancel_vacation_without_closing_returns_204(db, default_tenant, admin, emp):
    vr = VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2027, 3, 2),
        end_date=date(2027, 3, 3), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.APPROVED.value)
    db.add(vr)
    db.commit()
    db.refresh(vr)
    r = _client_as(db, emp).delete(f"/api/vacation-requests/{vr.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 204, r.text


# --- Fix #7: YearCarryover.source provenance ----------------------------------


def test_delete_year_closing_keeps_manual_carryover(db, default_tenant, admin, emp):
    other = _make_user(db, "emp2")
    # emp: a year-closing carryover for 2026.
    calculation_service.create_year_closing(db, 2025, [emp])
    yc_closing = db.query(YearCarryover).filter(
        YearCarryover.user_id == emp.id, YearCarryover.year == 2026).first()
    assert yc_closing is not None and yc_closing.source == "year_closing"

    # other: a MANUAL carryover for 2026 via the admin endpoint.
    client = _client_as(db, admin)
    r = client.put(f"/api/admin/users/{other.id}/carryovers/2026",
                   json={"overtime_hours": 3.0, "vacation_days": 5.0})
    assert r.status_code == 200, r.text
    yc_manual = db.query(YearCarryover).filter(
        YearCarryover.user_id == other.id, YearCarryover.year == 2026).first()
    assert yc_manual is not None and yc_manual.source == "manual"

    # Undo the 2025 closing → only the year_closing row goes, manual survives.
    d = client.delete("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert d.status_code == 200, d.text
    assert d.json()["deleted_count"] == 1

    db.expire_all()
    assert db.query(YearCarryover).filter(
        YearCarryover.user_id == emp.id, YearCarryover.year == 2026).first() is None
    surviving = db.query(YearCarryover).filter(
        YearCarryover.user_id == other.id, YearCarryover.year == 2026).first()
    assert surviving is not None
    assert surviving.source == "manual"


def test_delete_closure_after_closing_returns_stale_warning(db, default_tenant, admin, emp):
    _set_toggle(db, False)
    # Create a 2027 closure, then close 2027 → carryover 2028 exists.
    client = _client_as(db, admin)
    c = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": "2027-03-01", "end_date": "2027-03-04",
        "counts_as_vacation": True})
    assert c.status_code == 201, c.text
    calculation_service.create_year_closing(db, 2027, [emp, admin])
    r = client.delete(f"/api/company-closures/{c.json()['id']}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert "Jahresabschluss 2027" in r.json()["warning"]


def test_carryover_vacation_days_two_decimals(db, admin, emp):
    """#383-Reopen (philvdb): der Urlaubs-Übertrag muss 2 Nachkommastellen halten
    (krumme Werte, z. B. 3,33). Round-Trip über die Admin-Endpoint + Modell.
    (Präzision selbst = Numeric(5,2), auf Postgres verifiziert; SQLite ignoriert
    die Skala, daher hier v. a. Schema-/Flow-Guard.)"""
    client = _client_as(db, admin)
    r = client.put(f"/api/admin/users/{emp.id}/carryovers/2026",
                   json={"overtime_hours": 0.0, "vacation_days": 3.33})
    assert r.status_code == 200, r.text
    assert float(r.json()["vacation_days"]) == 3.33
    lst = client.get(f"/api/admin/users/{emp.id}/carryovers").json()
    row = next(c for c in lst if c["year"] == 2026)
    assert float(row["vacation_days"]) == 3.33
    _app.dependency_overrides.clear()
