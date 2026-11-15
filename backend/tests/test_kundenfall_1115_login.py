"""Kundenfall 2026-11-15, Log-Audit Punkt 12 (NET-4): Fehlversuche mit einem
Leerzeichen am Ende des Benutzernamens, und Sperren sah die Verwaltung nicht.

- Der Login-Name wird beim Login getrimmt (gespeicherte Namen bleiben).
- Erreicht ein Konto die Sperrgrenze, steht genau eine ``account_locked``-Zeile
  in ``security_events`` (subject = Konto, actor ``login:<ip>``, nie das Passwort).
"""
import pytest

from app.models.security_event import EVENT_ACCOUNT_LOCKED, SecurityEvent
from app.routers import auth as auth_router
from app.schemas.user import LoginRequest
from tests.test_auth_logging import login_client, _login  # noqa: F401
from tests.test_endpoints import _db_session, tenant, employee_user  # noqa: F401

SECRET = "Falsch-DoNotStore-4711!"


@pytest.fixture(autouse=True)
def _clean_tracker():
    auth_router._failed_logins.clear()
    yield
    auth_router._failed_logins.clear()


def test_schema_strips_username():
    assert LoginRequest(username="  employee \t", password="x").username == "employee"


def test_whitespace_only_username_rejected():
    with pytest.raises(Exception):
        LoginRequest(username="   ", password="x")


def test_login_with_trailing_space_succeeds(login_client, employee_user):
    r = _login(login_client, "employee ", "Employee2025!")
    assert r.status_code == 200, r.text


def test_lockout_writes_one_security_event(login_client, employee_user, _db_session):
    for _ in range(auth_router._LOCKOUT_ATTEMPTS):
        _login(login_client, "employee", SECRET)
    assert _login(login_client, "employee", SECRET).status_code == 429
    assert _login(login_client, "employee", SECRET).status_code == 429
    rows = _db_session.query(SecurityEvent).filter(SecurityEvent.event == EVENT_ACCOUNT_LOCKED).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.subject_user_id == employee_user.id
    assert row.tenant_id == employee_user.tenant_id
    assert row.actor.startswith("login:")
    assert SECRET not in (row.detail or "") and SECRET not in row.actor
    assert "gesperrt" in row.detail


def test_unknown_user_lockout_writes_no_event(login_client, employee_user, _db_session):
    for _ in range(auth_router._LOCKOUT_ATTEMPTS + 1):
        _login(login_client, "niemand", SECRET)
    assert _db_session.query(SecurityEvent).filter(
        SecurityEvent.event == EVENT_ACCOUNT_LOCKED).count() == 0


def test_event_constant_fits_column():
    assert len(EVENT_ACCOUNT_LOCKED) <= 50


def test_stored_name_with_trailing_space_can_still_log_in(login_client, employee_user, _db_session):
    """Review-Fund: ein Altkonto 'employee ' (Name mit Leerzeichen eingefuegt) darf
    durch das Trimmen der Eingabe nicht ausgesperrt werden."""
    employee_user.username = "employee "
    _db_session.commit()
    assert _login(login_client, "employee", "Employee2025!").status_code == 200
    assert _login(login_client, "employee ", "Employee2025!").status_code == 200


def test_user_schemas_strip_username():
    from app.schemas.user import UserUpdate
    assert UserUpdate(username="  anna  ").username == "anna"
    with pytest.raises(Exception):
        UserUpdate(username="   ")


from tests.test_endpoints import admin_client, admin_user  # noqa: E402,F401


def test_create_user_strips_and_sees_legacy_trailing_space_duplicate(admin_client, employee_user, _db_session):
    employee_user.username = "employee "
    _db_session.commit()
    body = {"username": "  employee", "first_name": "E", "last_name": "M", "weekly_hours": 40.0,
            "vacation_days": 30, "work_days_per_week": 5, "password": "EmployeeNeu2025!"}
    r = admin_client.post("/api/admin/users", json=body)
    assert r.status_code == 400 and "vergeben" in r.json()["detail"]
    r = admin_client.post("/api/admin/users", json={**body, "username": " neu "})
    assert r.status_code == 201, r.text
    assert r.json()["user"]["username"] == "neu"


def test_rename_legacy_trailing_space_to_trimmed_is_no_conflict(admin_client, employee_user, _db_session):
    employee_user.username = "employee "
    _db_session.commit()
    r = admin_client.put(f"/api/admin/users/{employee_user.id}", json={"username": "employee"})
    assert r.status_code == 200, r.text
    _db_session.refresh(employee_user)
    assert employee_user.username == "employee"
