"""Tests for admin-managed custom holidays (Issue #143).

Covers:
* API CRUD: create custom holiday (admin), reject duplicate, edit/delete.
* Standard (workalendar) holidays are not editable/deletable (403).
* Tenant isolation (F-026): admin of Tenant A cannot touch Tenant B holidays.
* Resync preserves admin holidays, regenerates only workalendar ones (REQ-3).
* A custom holiday reduces the monthly Sollzeit identically to a standard
  holiday (REQ-4).

API tests reuse the SQLite ``test_app`` + dependency-override pattern from
test_cross_tenant_api.py; service/calculation tests use the shared ``db`` /
``default_tenant`` / ``test_user`` fixtures from conftest.py.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.public_holiday import PublicHoliday
from app.models.tenant import Tenant
from app.services import auth_service, holiday_service
from app.services.calculation_service import get_monthly_target
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal
from tests.test_endpoints import test_app

TENANT_A_ID = uuid.UUID("aaaaaaaa-1430-4000-8000-000000000143")
TENANT_B_ID = uuid.UUID("bbbbbbbb-1430-4000-8000-000000000143")


# ─── API fixtures (SQLite, dependency-overridden) ────────────────────────


@pytest.fixture(scope="function")
def _db_session():
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.commit()
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.commit()
        Base.metadata.drop_all(bind=engine, checkfirst=True)
    # Process-local holiday cache must not leak across tests.
    holiday_service.invalidate_holiday_cache()


@pytest.fixture(scope="function")
def two_tenants(_db_session):
    for tid, name in [(TENANT_A_ID, "Tenant A"), (TENANT_B_ID, "Tenant B")]:
        _db_session.add(Tenant(id=tid, name=name, slug=f"t-{tid.hex[:8]}", is_active=True, mode="multi"))
    _db_session.commit()
    return TENANT_A_ID, TENANT_B_ID


def _make_admin(db, tenant_id, username):
    u = User(
        username=username,
        email=f"{username}@test.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture(scope="function")
def admin_a(_db_session, two_tenants):
    return _make_admin(_db_session, TENANT_A_ID, "admin_a_143")


@pytest.fixture(scope="function")
def client_as_admin_a(_db_session, admin_a):
    def _override_db():
        yield _db_session

    def _current():
        return admin_a

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _current
    test_app.dependency_overrides[require_admin] = _current

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


# ─── API: create / list ───────────────────────────────────────────────────


def test_create_custom_holiday(client_as_admin_a):
    """POST /api/holidays creates a custom holiday (is_custom, source='admin')."""
    resp = client_as_admin_a.post(
        "/api/holidays/",
        json={"name": "Schützenfest", "date": "2026-07-06"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Schützenfest"
    assert body["date"] == "2026-07-06"
    assert body["year"] == 2026
    assert body["is_custom"] is True
    assert "id" in body


def test_create_custom_holiday_persists_source_admin(_db_session, client_as_admin_a):
    """The persisted row carries source='admin' so a resync preserves it."""
    resp = client_as_admin_a.post(
        "/api/holidays/", json={"name": "Karneval", "date": "2026-02-16"}
    )
    assert resp.status_code == 201, resp.text
    row = _db_session.query(PublicHoliday).filter(PublicHoliday.name == "Karneval").first()
    assert row is not None
    assert row.source == "admin"
    assert row.is_custom is True
    assert row.tenant_id == TENANT_A_ID


def test_create_custom_holiday_rejects_blank_name(client_as_admin_a):
    """A blank name is rejected (422 validation)."""
    resp = client_as_admin_a.post(
        "/api/holidays/", json={"name": "   ", "date": "2026-07-06"}
    )
    assert resp.status_code == 422, resp.text


def test_create_custom_holiday_rejects_duplicate_date(_db_session, client_as_admin_a):
    """Two holidays on the same tenant+date are rejected (409)."""
    first = client_as_admin_a.post(
        "/api/holidays/", json={"name": "Schützenfest", "date": "2026-07-06"}
    )
    assert first.status_code == 201, first.text
    dup = client_as_admin_a.post(
        "/api/holidays/", json={"name": "Anderes Fest", "date": "2026-07-06"}
    )
    assert dup.status_code == 409, dup.text


def test_create_custom_holiday_rejects_duplicate_of_standard(_db_session, client_as_admin_a):
    """A custom holiday cannot be created on a date a workalendar holiday already occupies."""
    std = PublicHoliday(
        date=date(2026, 12, 25), name="1. Weihnachtstag", year=2026,
        tenant_id=TENANT_A_ID, is_custom=False, source="workalendar",
    )
    _db_session.add(std)
    _db_session.commit()

    dup = client_as_admin_a.post(
        "/api/holidays/", json={"name": "Eigener Tag", "date": "2026-12-25"}
    )
    assert dup.status_code == 409, dup.text


def test_list_holidays_returns_standard_and_custom(_db_session, client_as_admin_a):
    """GET returns both standard and custom holidays with is_custom flag."""
    std = PublicHoliday(
        date=date(2026, 1, 1), name="Neujahr", year=2026,
        tenant_id=TENANT_A_ID, is_custom=False, source="workalendar",
    )
    custom = PublicHoliday(
        date=date(2026, 7, 6), name="Schützenfest", year=2026,
        tenant_id=TENANT_A_ID, is_custom=True, source="admin",
    )
    _db_session.add_all([std, custom])
    _db_session.commit()

    resp = client_as_admin_a.get("/api/holidays/?year=2026")
    assert resp.status_code == 200, resp.text
    by_name = {h["name"]: h for h in resp.json()}
    assert by_name["Neujahr"]["is_custom"] is False
    assert by_name["Schützenfest"]["is_custom"] is True


# ─── API: update / delete + standard-holiday protection ───────────────────


def test_update_custom_holiday(_db_session, client_as_admin_a):
    """PUT edits a custom holiday's name and date."""
    custom = PublicHoliday(
        date=date(2026, 7, 6), name="Schützenfest", year=2026,
        tenant_id=TENANT_A_ID, is_custom=True, source="admin",
    )
    _db_session.add(custom)
    _db_session.commit()
    hid = str(custom.id)

    resp = client_as_admin_a.put(
        f"/api/holidays/{hid}", json={"name": "Schützenfest (verschoben)", "date": "2027-07-05"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Schützenfest (verschoben)"
    assert body["date"] == "2027-07-05"
    assert body["year"] == 2027


def test_delete_custom_holiday(_db_session, client_as_admin_a):
    """DELETE removes a custom holiday."""
    custom = PublicHoliday(
        date=date(2026, 7, 6), name="Schützenfest", year=2026,
        tenant_id=TENANT_A_ID, is_custom=True, source="admin",
    )
    _db_session.add(custom)
    _db_session.commit()
    hid = str(custom.id)

    resp = client_as_admin_a.delete(f"/api/holidays/{hid}")
    assert resp.status_code == 204, resp.text
    _db_session.expire_all()
    assert _db_session.query(PublicHoliday).filter(PublicHoliday.id == custom.id).first() is None


def test_standard_holiday_not_deletable(_db_session, client_as_admin_a):
    """Standard (workalendar) holidays cannot be deleted — returns 403."""
    std = PublicHoliday(
        date=date(2026, 1, 1), name="Neujahr", year=2026,
        tenant_id=TENANT_A_ID, is_custom=False, source="workalendar",
    )
    _db_session.add(std)
    _db_session.commit()
    hid = str(std.id)

    resp = client_as_admin_a.delete(f"/api/holidays/{hid}")
    assert resp.status_code == 403, resp.text

    _db_session.expire_all()
    assert _db_session.query(PublicHoliday).filter(PublicHoliday.id == std.id).first() is not None


def test_standard_holiday_not_editable(_db_session, client_as_admin_a):
    """Standard (workalendar) holidays cannot be edited — returns 403."""
    std = PublicHoliday(
        date=date(2026, 1, 1), name="Neujahr", year=2026,
        tenant_id=TENANT_A_ID, is_custom=False, source="workalendar",
    )
    _db_session.add(std)
    _db_session.commit()
    hid = str(std.id)

    resp = client_as_admin_a.put(f"/api/holidays/{hid}", json={"name": "Gehackt"})
    assert resp.status_code == 403, resp.text

    _db_session.expire_all()
    assert _db_session.query(PublicHoliday).filter(PublicHoliday.id == std.id).first().name == "Neujahr"


# ─── API: tenant isolation (F-026) ────────────────────────────────────────


def test_admin_a_cannot_delete_tenant_b_custom_holiday(_db_session, client_as_admin_a):
    """A custom holiday owned by Tenant B must 404 for Tenant A's admin."""
    h_b = PublicHoliday(
        date=date(2026, 7, 6), name="B-Fest", year=2026,
        tenant_id=TENANT_B_ID, is_custom=True, source="admin",
    )
    _db_session.add(h_b)
    _db_session.commit()

    resp = client_as_admin_a.delete(f"/api/holidays/{h_b.id}")
    assert resp.status_code == 404, resp.text

    _db_session.expire_all()
    assert _db_session.query(PublicHoliday).filter(PublicHoliday.id == h_b.id).first() is not None


def test_admin_a_cannot_update_tenant_b_custom_holiday(_db_session, client_as_admin_a):
    """A custom holiday owned by Tenant B must 404 for Tenant A's admin on PUT."""
    h_b = PublicHoliday(
        date=date(2026, 7, 6), name="B-Fest", year=2026,
        tenant_id=TENANT_B_ID, is_custom=True, source="admin",
    )
    _db_session.add(h_b)
    _db_session.commit()

    resp = client_as_admin_a.put(f"/api/holidays/{h_b.id}", json={"name": "Gehackt"})
    assert resp.status_code == 404, resp.text

    _db_session.expire_all()
    assert _db_session.query(PublicHoliday).filter(PublicHoliday.id == h_b.id).first().name == "B-Fest"


# ─── Service: resync preserves admin holidays (REQ-3) ─────────────────────


class TestResyncPreservesCustom:
    def test_delete_all_holidays_with_source_filter_keeps_admin(self, db, default_tenant):
        """delete_all_holidays(source='workalendar') keeps source='admin' rows."""
        std = PublicHoliday(
            date=date(2026, 1, 1), name="Neujahr", year=2026,
            tenant_id=DEFAULT_TENANT_ID, is_custom=False, source="workalendar",
        )
        custom = PublicHoliday(
            date=date(2026, 7, 6), name="Schützenfest", year=2026,
            tenant_id=DEFAULT_TENANT_ID, is_custom=True, source="admin",
        )
        db.add_all([std, custom])
        db.commit()

        deleted = holiday_service.delete_all_holidays(
            db, tenant_id=DEFAULT_TENANT_ID, source="workalendar"
        )
        db.commit()

        assert deleted == 1
        remaining = db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == DEFAULT_TENANT_ID
        ).all()
        assert len(remaining) == 1
        assert remaining[0].name == "Schützenfest"
        assert remaining[0].source == "admin"

    def test_resync_flow_preserves_custom_holiday(self, db, default_tenant):
        """The full delete(source='workalendar') + sync flow keeps the custom row."""
        custom = PublicHoliday(
            date=date(2026, 7, 6), name="Schützenfest", year=2026,
            tenant_id=DEFAULT_TENANT_ID, is_custom=True, source="admin",
        )
        db.add(custom)
        db.commit()

        # Simulate the admin_settings resync flow.
        holiday_service.delete_all_holidays(db, tenant_id=DEFAULT_TENANT_ID, source="workalendar")
        holiday_service.sync_current_and_next_year(db, state="Bayern", tenant_id=DEFAULT_TENANT_ID)

        still_there = db.query(PublicHoliday).filter(
            PublicHoliday.name == "Schützenfest",
            PublicHoliday.tenant_id == DEFAULT_TENANT_ID,
        ).first()
        assert still_there is not None
        assert still_there.source == "admin"
        # Workalendar holidays were (re)generated alongside it.
        wk_count = db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == DEFAULT_TENANT_ID,
            PublicHoliday.source == "workalendar",
        ).count()
        assert wk_count > 0

    def test_sync_does_not_rename_admin_holiday_on_shared_date(self, db, default_tenant):
        """If an admin holiday shares a date with a workalendar holiday, its name survives a sync."""
        # New Year's Day is a Bavarian workalendar holiday; put a custom one there.
        custom = PublicHoliday(
            date=date(2026, 1, 1), name="Mein Eigener Neujahrstag", year=2026,
            tenant_id=DEFAULT_TENANT_ID, is_custom=True, source="admin",
        )
        db.add(custom)
        db.commit()

        holiday_service.sync_holidays(db, 2026, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
        db.commit()

        row = db.query(PublicHoliday).filter(
            PublicHoliday.date == date(2026, 1, 1),
            PublicHoliday.tenant_id == DEFAULT_TENANT_ID,
        ).all()
        # Only the admin row remains on that date — its name is untouched.
        assert len(row) == 1
        assert row[0].name == "Mein Eigener Neujahrstag"
        assert row[0].source == "admin"


# ─── Calculation: custom holiday reduces Sollzeit (REQ-4) ──────────────────


def test_custom_holiday_reduces_monthly_target(db, default_tenant, test_user):
    """A custom holiday on a weekday reduces the monthly Sollzeit by one workday."""
    # 2026-07-06 is a Monday — a working day for the 5-day, 40h test_user.
    target_before = get_monthly_target(db, test_user, 2026, 7)

    custom = PublicHoliday(
        date=date(2026, 7, 6), name="Schützenfest", year=2026,
        tenant_id=DEFAULT_TENANT_ID, is_custom=True, source="admin",
    )
    db.add(custom)
    db.commit()

    target_after = get_monthly_target(db, test_user, 2026, 7)

    # 40h / 5 days = 8h per workday reduction.
    assert target_after == (target_before - Decimal("8.00"))
