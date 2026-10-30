"""1.21 Teamübersicht der Arbeitszeiten: ``GET /api/admin/team-schedule?date=``.

Je aktive, sichtbare Person der zu einem Datum gültige Vertrags-Snapshot
(Blöcke, Wochenstunden, Tagesplan) plus die nächste spätere Änderung. Rein
lesend; geschrieben wird weiter nur über ``POST .../working-hours-changes``.
"""
import uuid
from datetime import date

from app.models import User, UserRole, WorkingHoursChange
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import block_week, legacy_week

OLD = block_week(mon=[("07:30", "13:00"), ("15:00", "18:00")])
NEW = block_week(tue=[("07:30", "13:00")], thu=[("15:00", "18:00")])
SWITCH = date(2026, 10, 12)


def _person(db, first, last, *, department=None, blocks=None, active=True, hidden=False, track_hours=True):
    u = User(
        username=f"{first.lower()}_{uuid.uuid4().hex[:6]}", email=f"{first.lower()}@x.de",
        password_hash=auth_service.hash_password("Irrelevant2025!"), first_name=first, last_name=last,
        role=UserRole.EMPLOYEE, weekly_hours=8.5, work_days_per_week=1, vacation_days=30,
        tenant_id=DEFAULT_TENANT_ID, department=department, work_blocks=blocks, is_active=active,
        is_hidden=hidden, track_hours=track_hours, calendar_color="#AABBCC",
    )
    db.add(u)
    db.commit()
    return u


def _change(db, user, eff, week):
    db.add(WorkingHoursChange(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, effective_from=eff, weekly_hours=8.5,
        use_daily_schedule=True, hours_monday=0, hours_tuesday=5.5, hours_wednesday=0,
        hours_thursday=3, hours_friday=0, work_days_per_week=2, blocks=week,
    ))
    db.commit()


def _rows(client, d):
    r = client.get(f"/api/admin/team-schedule?date={d.isoformat()}")
    assert r.status_code == 200, r.text
    return {row["last_name"]: row for row in r.json()}


def test_rows_resolve_the_snapshot_of_the_date_and_name_the_next_change(_db_session, admin_client):
    anna = _person(_db_session, "Anna", "Arzt", department="Ärzte", blocks=OLD)
    _change(_db_session, anna, SWITCH, NEW)

    before = _rows(admin_client, date(2026, 10, 8))["Arzt"]
    assert before["blocks"] == OLD
    assert before["next_change"]["effective_from"] == SWITCH.isoformat()
    assert before["next_change"]["blocks"] == NEW
    assert (before["department"], before["calendar_color"], before["legacy"]) == ("Ärzte", "#AABBCC", False)

    after = _rows(admin_client, SWITCH)["Arzt"]
    assert after["blocks"] == NEW
    assert after["next_change"] is None
    assert after["schedule"]["hours_tuesday"] == 5.5
    assert after["schedule"]["work_days_per_week"] == 2


def test_only_active_visible_people_sorted_by_name(_db_session, admin_client, admin_user):
    _person(_db_session, "Zora", "Zander", department="MFA", blocks=NEW)
    _person(_db_session, "Bert", "Berg", department="MFA")
    _person(_db_session, "Inge", "Inaktiv", active=False)
    _person(_db_session, "Hans", "Hidden", hidden=True)
    resp = admin_client.get("/api/admin/team-schedule?date=2026-10-20")
    names = [r["last_name"] for r in resp.json()]
    assert "Inaktiv" not in names and "Hidden" not in names
    assert names == sorted(names)
    berg = _rows(admin_client, date(2026, 10, 20))["Berg"]
    assert (berg["blocks"], berg["legacy"], berg["track_hours"]) == (None, False, True)


def test_legacy_window_is_flagged(_db_session, admin_client):
    _person(_db_session, "Leo", "Legacy", blocks=legacy_week(mon=("07:37", "23:59")))
    assert _rows(admin_client, date(2026, 10, 20))["Legacy"]["legacy"] is True


def test_date_defaults_to_today(_db_session, admin_client):
    _person(_db_session, "Tim", "Today", blocks=NEW)
    resp = admin_client.get("/api/admin/team-schedule")
    assert resp.status_code == 200
    assert any(r["last_name"] == "Today" for r in resp.json())


def test_employees_are_rejected(_db_session, employee_client):
    assert employee_client.get("/api/admin/team-schedule").status_code == 403
