"""Spec 2026-10-08, 11.1/11.4/11.5 (PR1): Benutzer-API und Arbeitszeit-Blöcke.

* Altfelder ``scheduled_*`` → 400 „Bitte Seite neu laden" (E26), erkannt am Präfix.
* ``work_blocks`` per PUT → 400 (E27, genau ein Schreibweg).
* Leseschemas LOCKER (E29): Altwerte wie 07:37 oder der Platzhalter 23:59
  dürfen weder Login noch Benutzerliste in einen HTTP 500 verwandeln.
* ``work_blocks_today`` ist datumsaufgelöst (11.1) — eine zukunftsdatierte
  Verlaufszeile wirkt heute noch nicht.
"""
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_db
from app.models import WorkingHoursChange
from app.routers.admin_users import LEGACY_WINDOW_FIELDS_DETAIL
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_user, endpoints_app, tenant,
)
from tests.work_blocks_fixtures import legacy_week

# 07:37 (kein 5-Minuten-Raster) und der Platzhalter 23:59 aus Migration 073.
ODD = legacy_week(mon=("07:37", "16:30"), fri=("07:30", None))
LATER = legacy_week(mon=("09:00", "17:00"))
NEW_USER = {
    "username": "neu", "first_name": "Neu", "last_name": "Person", "weekly_hours": 40.0,
    "vacation_days": 30, "work_days_per_week": 5, "password": "NeuPerson2025!",
}


def test_legacy_detail_text_is_the_spec_text():
    assert LEGACY_WINDOW_FIELDS_DETAIL == (
        "Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) "
        "wurden durch Arbeitszeit-Blöcke ersetzt."
    )


def test_put_with_work_blocks_is_400(admin_client, employee_user):
    resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={"work_blocks": ODD})
    assert resp.status_code == 400, resp.text
    assert "Arbeitszeit-Blöcke" in resp.json()["detail"]


def test_put_with_legacy_prefix_is_400_and_changes_nothing(admin_client, employee_user, _db_session):
    resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={
        "first_name": "Neu", "scheduled_start_monday": "08:00"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == LEGACY_WINDOW_FIELDS_DETAIL
    _db_session.refresh(employee_user)
    assert employee_user.first_name == "Max"


def test_post_with_legacy_prefix_is_400(admin_client):
    resp = admin_client.post("/api/admin/users", json={**NEW_USER, "scheduled_end_friday": "15:00"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == LEGACY_WINDOW_FIELDS_DETAIL


def test_post_without_legacy_fields_has_no_window_keys(admin_client):
    resp = admin_client.post("/api/admin/users", json=NEW_USER)
    assert resp.status_code == 201, resp.text
    body = resp.json()["user"]
    assert [k for k in body if k.startswith("scheduled_")] == []
    assert body["work_blocks"] is None
    assert body["work_blocks_today"] is None


def test_list_and_get_resolve_work_blocks_today(admin_client, employee_user, _db_session):
    employee_user.work_blocks = ODD
    _db_session.add(WorkingHoursChange(
        user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=today_local() + timedelta(days=1), weekly_hours=40,
        use_daily_schedule=False, work_days_per_week=5, blocks=LATER,
    ))
    _db_session.commit()
    listed = next(u for u in admin_client.get("/api/admin/users").json()
                  if u["id"] == str(employee_user.id))
    assert listed["work_blocks"] == ODD
    assert listed["work_blocks_today"] == ODD  # die Zeile ab morgen wirkt heute nicht
    single = admin_client.get(f"/api/admin/users/{employee_user.id}")
    assert single.status_code == 200, single.text
    assert single.json()["work_blocks_today"] == ODD


def test_structurally_broken_blocks_do_not_break_the_list(admin_client, employee_user, _db_session):
    employee_user.work_blocks = [{"blocks": "kaputt", "pause_minutes": None}] * 5
    _db_session.commit()
    resp = admin_client.get("/api/admin/users")
    assert resp.status_code == 200, resp.text
    listed = next(u for u in resp.json() if u["id"] == str(employee_user.id))
    assert listed["work_blocks_today"] is None


def test_login_with_legacy_blocks_is_200(_db_session, employee_user):
    employee_user.work_blocks = ODD
    _db_session.commit()

    def _override_db():
        yield _db_session

    endpoints_app.dependency_overrides[get_db] = _override_db
    try:
        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(endpoints_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "employee", "password": "Employee2025!"})
    finally:
        endpoints_app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["work_blocks"] == ODD
    assert resp.json()["user"]["work_blocks_today"] == ODD


def test_impersonation_response_carries_work_blocks_today(admin_client, employee_user, _db_session):
    """Spec 11.1: die Impersonation-Antwort trägt dieselben Felder wie der Login."""
    employee_user.work_blocks = ODD
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/impersonate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["work_blocks"] == ODD
    assert resp.json()["user"]["work_blocks_today"] == ODD
