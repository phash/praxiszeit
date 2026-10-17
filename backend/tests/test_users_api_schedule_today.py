"""Gesamtreview 1.20 (Fund 25): Benutzerliste und -formular zeigen den HEUTE
gültigen Vertragsstand, nicht die User-Zeile.

Die User-Zeile (``weekly_hours``, ``use_daily_schedule``, ``hours_*``,
``work_days_per_week``) spiegelt der Server nur beim Anlegen oder Löschen einer
Verlaufszeile (``_sync_user_to_current_change``; kein Scheduler, Spec 9.8). Eine
zukunftsdatierte Änderung kommt nach ihrem Wirkungsdatum also erst beim nächsten
Schreibvorgang dort an. Daneben stand im Bearbeiten-Formular schon der
datumsaufgelöste ``work_blocks_today`` — das Formular widersprach sich
(„40 h/Woche · Einheitliche Tagesstunden" über „Mo 08:00–12:00 …").

``schedule_today`` trägt deshalb die vier Werte aus demselben Resolver
(``get_schedule_for_date``) wie ``work_blocks_today``.
"""
from datetime import timedelta

from fastapi.testclient import TestClient
from unittest.mock import patch

from app.database import get_db
from app.models import WorkingHoursChange
from app.services import calculation_service
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_user, endpoints_app, tenant,
)
from tests.work_blocks_fixtures import block_week

HALF_DAYS = block_week(**{d: [("08:00", "12:00")] for d in ("mon", "tue", "wed", "thu", "fri")})

TWENTY_FROM_BLOCKS = {
    "weekly_hours": 20.0,
    "use_daily_schedule": True,
    "hours_monday": 4.0,
    "hours_tuesday": 4.0,
    "hours_wednesday": 4.0,
    "hours_thursday": 4.0,
    "hours_friday": 4.0,
    "work_days_per_week": 5,
}


def _unsynced_change(user, *, days_from_today):
    """Verlaufszeile OHNE den Spiegel auf die User-Zeile — der Stand nach dem
    Wirkungsdatum einer zukunftsdatierten Änderung."""
    return WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=today_local() + timedelta(days=days_from_today),
        weekly_hours=20, use_daily_schedule=True, work_days_per_week=5,
        hours_monday=4, hours_tuesday=4, hours_wednesday=4, hours_thursday=4, hours_friday=4,
        blocks=HALF_DAYS,
    )


def test_list_carries_the_schedule_valid_today(admin_client, employee_user, _db_session):
    _db_session.add(_unsynced_change(employee_user, days_from_today=-4))
    _db_session.commit()
    listed = next(u for u in admin_client.get("/api/admin/users").json()
                  if u["id"] == str(employee_user.id))
    assert listed["weekly_hours"] == 40.0  # User-Zeile, noch nicht nachgezogen
    assert listed["schedule_today"] == TWENTY_FROM_BLOCKS
    assert listed["work_blocks_today"] == HALF_DAYS  # derselbe Stand wie die Blöcke


def test_future_change_does_not_act_today(admin_client, employee_user, _db_session):
    _db_session.add(_unsynced_change(employee_user, days_from_today=1))
    _db_session.commit()
    listed = next(u for u in admin_client.get("/api/admin/users").json()
                  if u["id"] == str(employee_user.id))
    assert listed["schedule_today"] == {
        "weekly_hours": 40.0, "use_daily_schedule": False,
        "hours_monday": None, "hours_tuesday": None, "hours_wednesday": None,
        "hours_thursday": None, "hours_friday": None, "work_days_per_week": 5,
    }


def test_single_user_get_and_put_carry_schedule_today(admin_client, employee_user, _db_session):
    _db_session.add(_unsynced_change(employee_user, days_from_today=0))
    _db_session.commit()
    single = admin_client.get(f"/api/admin/users/{employee_user.id}")
    assert single.status_code == 200, single.text
    assert single.json()["schedule_today"] == TWENTY_FROM_BLOCKS
    put = admin_client.put(f"/api/admin/users/{employee_user.id}", json={"first_name": "Moritz"})
    assert put.status_code == 200, put.text
    assert put.json()["schedule_today"] == TWENTY_FROM_BLOCKS


def test_login_carries_schedule_today(_db_session, employee_user):
    _db_session.add(_unsynced_change(employee_user, days_from_today=-1))
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
    assert resp.json()["user"]["schedule_today"] == TWENTY_FROM_BLOCKS


def test_attach_without_history_mirrors_the_user_row(_db_session, employee_user):
    calculation_service.attach_work_blocks_today(_db_session, [employee_user], today_local())
    assert employee_user.schedule_today == {
        "weekly_hours": 40.0, "use_daily_schedule": False,
        "hours_monday": None, "hours_tuesday": None, "hours_wednesday": None,
        "hours_thursday": None, "hours_friday": None, "work_days_per_week": 5,
    }
