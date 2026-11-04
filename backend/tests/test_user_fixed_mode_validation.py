"""#377 Baustein 2b: use_fixed_monthly_target Schema-Feld + Validierung.

Harness wie backend/tests/test_milog.py (lokale _app() + dependency_overrides,
/api-Pfade, headerloser TestClient).
"""
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

USERS = "/api/admin/users"


def _app() -> FastAPI:
    from app.routers import admin
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    a = FastAPI()
    limiter.enabled = False
    a.state.limiter = limiter
    a.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    a.include_router(admin.router)
    return a


app = _app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    """WHC_EFF (2027-01-01) muss in der Zukunft bleiben, sonst wird der POST ab
    2027-01-02 zur rückwirkenden Verkürzung (400 ohne Grund)."""
    from datetime import date
    from tests.wh_change_helpers import freeze
    freeze(monkeypatch, date(2026, 11, 3))


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="D", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, username, role=UserRole.EMPLOYEE, weekly=Decimal("40")):
    u = User(username=username, email=f"{username}@x.de",
             password_hash=auth_service.hash_password("test123"),
             first_name=username, last_name="T", role=role, weekly_hours=weekly,
             vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "admin1", role=UserRole.ADMIN, weekly=Decimal("40"))


def _client_as(db, user, admin_user):
    def od():
        yield db
    app.dependency_overrides[get_db] = od
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


BASE_PAYLOAD = {
    "username": "fx", "first_name": "F", "last_name": "X", "password": "E2ePass1234!",
    "role": "employee", "weekly_hours": 40, "vacation_days": 30, "work_days_per_week": 5,
}


# --------------------------------------------------------------------------- #
# UserCreate validation
# --------------------------------------------------------------------------- #
def test_create_fixed_target_without_agreed_hours_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "use_fixed_monthly_target": True,
        "track_hours": True,
        "milog_working_time_account": True,
        # agreed_monthly_hours missing
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_fixed_target_with_track_hours_false_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": False,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_fixed_target_with_milog_false_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": False,
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_fixed_target_with_all_requirements_ok(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 201, resp.text
    uid = resp.json()["user"]["id"]
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert row["use_fixed_monthly_target"] is True
    assert row["agreed_monthly_hours"] == 173.3
    app.dependency_overrides.clear()


def test_create_without_fixed_target_ignores_missing_agreed(db, admin, default_tenant):
    # Sanity: default flag False must NOT trigger the new validator at all.
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={**BASE_PAYLOAD, "username": "plain"})
    assert resp.status_code == 201, resp.text
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# UserUpdate validation (partial payloads)
# --------------------------------------------------------------------------- #
def _create_plain_user(client, username="upduser"):
    resp = client.post(USERS, json={**BASE_PAYLOAD, "username": username})
    assert resp.status_code == 201, resp.text
    return resp.json()["user"]["id"]


# --------------------------------------------------------------------------- #
# Teil A (Vertragsverlauf): die vier Felder sind historisiert. PUT lehnt sie ab
# (400); geändert werden sie über die Arbeitszeit-Änderung, und die Regel prüft
# den ZUSAMMENGEFÜHRTEN Snapshot (gesendet + vom Wirkungsdatum geerbt).
# --------------------------------------------------------------------------- #
WHC_EFF = "2027-01-01"   # Monatserster (Minijob-Felder nur zum Monatsersten)
FIXED_AGREED = "Fester Monats-Soll braucht eine vereinbarte Monatsarbeitszeit (> 0)."
FIXED_TRACK = "Fester Monats-Soll setzt Stundenzählung (track_hours) voraus."
FIXED_MILOG = "Fester Monats-Soll setzt das MiLoG-Arbeitszeitkonto voraus."


def _whc(client, uid, **fields):
    return client.post(f"{USERS}/{uid}/working-hours-changes", json={
        "effective_from": WHC_EFF, "weekly_hours": 40, "work_days_per_week": 5, **fields,
    })


def test_update_turn_on_fixed_target_without_agreed_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd1")
    resp = _whc(client, uid, use_fixed_monthly_target=True, track_hours=True, milog_working_time_account=True)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == FIXED_AGREED
    app.dependency_overrides.clear()


def test_update_turn_on_fixed_target_with_track_hours_false_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd2")
    resp = _whc(client, uid, use_fixed_monthly_target=True, agreed_monthly_hours=173.3,
                track_hours=False, milog_working_time_account=True)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == FIXED_TRACK
    app.dependency_overrides.clear()


def test_update_turn_on_fixed_target_with_milog_false_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd3")
    resp = _whc(client, uid, use_fixed_monthly_target=True, agreed_monthly_hours=173.3,
                track_hours=True, milog_working_time_account=False)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == FIXED_MILOG
    app.dependency_overrides.clear()


def test_update_turn_on_fixed_target_omitted_fields_inherit_snapshot(db, admin, default_tenant):
    # Nicht gesendete Felder erben den Snapshot (track_hours True, MiLoG aus) —
    # geprüft wird der zusammengeführte Stand, nicht nur der Body.
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd4")
    resp = _whc(client, uid, use_fixed_monthly_target=True, agreed_monthly_hours=173.3)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == FIXED_MILOG
    app.dependency_overrides.clear()


def test_update_turn_on_fixed_target_with_all_requirements_ok(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd5")
    resp = _whc(client, uid, use_fixed_monthly_target=True, agreed_monthly_hours=173.3,
                track_hours=True, milog_working_time_account=True)
    assert resp.status_code == 201, resp.text
    assert resp.json()["use_fixed_monthly_target"] is True
    app.dependency_overrides.clear()


@pytest.mark.parametrize("payload", [
    {"use_fixed_monthly_target": True},
    {"use_fixed_monthly_target": True, "agreed_monthly_hours": 173.3,
     "track_hours": True, "milog_working_time_account": True},
])
def test_update_put_of_fixed_target_fields_is_locked(db, admin, default_tenant, payload):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd7")
    resp = client.put(f"{USERS}/{uid}", json=payload)
    assert resp.status_code == 400, resp.text
    assert client.get(f"{USERS}/{uid}").json()["use_fixed_monthly_target"] is False
    app.dependency_overrides.clear()


def test_update_unrelated_field_without_flag_unaffected(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd6")
    resp = client.put(f"{USERS}/{uid}", json={"first_name": "Changed"})
    assert resp.status_code == 200, resp.text
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Release-Review 1.15.0 (#377 Baustein 2b): eine Änderung, die eine
# Voraussetzung des festen Monats-Solls abschaltet, ohne den Schalter selbst
# mitzuschicken, darf keinen ungültigen Stand erzeugen. Seit Teil A: PUT ist
# gesperrt (400), und die Arbeitszeit-Änderung prüft den Snapshot (400).
# --------------------------------------------------------------------------- #
def _create_fixed_target_user(client, username):
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "username": username,
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["user"]["id"]


def _assert_still_fixed(client, uid):
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert row["use_fixed_monthly_target"] is True
    assert row["milog_working_time_account"] is True
    assert row["track_hours"] is True


def test_update_isolated_milog_off_on_fixed_target_user_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_fixed_target_user(client, "iso1")
    assert client.put(f"{USERS}/{uid}", json={"milog_working_time_account": False}).status_code == 400
    resp = _whc(client, uid, milog_working_time_account=False)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == FIXED_MILOG
    _assert_still_fixed(client, uid)
    app.dependency_overrides.clear()


def test_update_isolated_track_hours_off_on_fixed_target_user_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_fixed_target_user(client, "iso2")
    assert client.put(f"{USERS}/{uid}", json={"track_hours": False}).status_code == 400
    resp = _whc(client, uid, track_hours=False)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == FIXED_TRACK
    _assert_still_fixed(client, uid)
    app.dependency_overrides.clear()


def test_update_normal_field_on_fixed_target_user_still_ok(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_fixed_target_user(client, "iso3")
    resp = client.put(f"{USERS}/{uid}", json={"first_name": "Changed"})
    assert resp.status_code == 200, resp.text
    app.dependency_overrides.clear()


def test_update_disable_fixed_target_and_milog_together_ok(db, admin, default_tenant):
    # Den Schalter selbst in derselben Änderung abzuschalten ist der
    # dokumentierte Weg aus dem festen Monats-Soll.
    client = _client_as(db, admin, admin)
    uid = _create_fixed_target_user(client, "iso4")
    resp = _whc(client, uid, use_fixed_monthly_target=False, milog_working_time_account=False)
    assert resp.status_code == 201, resp.text
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# UserListResponse round-trip
# --------------------------------------------------------------------------- #
def test_userlist_carries_use_fixed_monthly_target(db, admin, default_tenant):
    # Regression: das Edit-Formular liest die Liste; fehlt das Feld dort,
    # setzt jeder Save es still auf Default (wie #376/#377-Lektion).
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "username": "listcheck",
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 201, resp.text
    uid = resp.json()["user"]["id"]
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert "use_fixed_monthly_target" in row
    assert row["use_fixed_monthly_target"] is True
    app.dependency_overrides.clear()


@pytest.mark.parametrize("payload", [
    {"vacation_days": 99}, {"agreed_monthly_hours": 0}, {"track_hours": "x"},
])
def test_put_of_contract_field_out_of_range_is_400_not_422(db, admin, default_tenant, payload):
    """F063: jeder Wert eines gesperrten Vertragsfelds erreicht die Sperre (400),
    kein Feld-Constraint macht daraus eine 422."""
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd_lock")
    resp = client.put(f"{USERS}/{uid}", json=payload)
    assert resp.status_code == 400, resp.text
    app.dependency_overrides.clear()


def test_whc_contract_numbers_rounded_like_the_column(db, admin, default_tenant):
    """F008/F028: Anspruch und Monatsstunden werden schon im Schema auf eine
    Stelle gerundet (kaufmännisch wie PostgreSQL) — Regel, Vorschau und Zeile
    sehen denselben Wert."""
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "round1")
    resp = _whc(client, uid, vacation_days=24.25, agreed_monthly_hours=40.04)
    assert resp.status_code == 201, resp.text
    assert resp.json()["vacation_days"] == 24.3
    assert resp.json()["agreed_monthly_hours"] == 40.0
    app.dependency_overrides.clear()


def test_whc_fixed_target_with_agreed_rounding_to_zero_is_422(db, admin, default_tenant):
    """F101: 0,04 h würde als 0,0 gespeichert — die Festes-Soll-Regel darf nicht
    an der Rundung vorbeilaufen."""
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "round2")
    resp = _whc(client, uid, use_fixed_monthly_target=True, agreed_monthly_hours=0.04,
                track_hours=True, milog_working_time_account=True)
    assert resp.status_code == 422, resp.text
    assert "mindestens 0,1" in resp.text
    app.dependency_overrides.clear()
