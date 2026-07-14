"""Fix #2: eine WorkingHoursChange ist für use_daily_schedule-MA wirkungslos
(get_daily_target_for_date liest dann nur hours_mon…fri, NICHT weekly_hours) →
die Stunden-Historie hätte null Effekt aufs Soll, die UI zeigte aber den neuen
Wert (stille falsche §16-Records). Entscheidung: solche Anträge mit HTTP 400
ablehnen, statt eine wirkungslose Historie zu schreiben.
"""
from datetime import date

import pytest
from fastapi import HTTPException

from app.models import User, UserRole, WorkingHoursChange
from app.routers.admin_users import create_working_hours_change
from app.schemas.working_hours_change import WorkingHoursChangeCreate
from tests.conftest import DEFAULT_TENANT_ID


def _make_user(db, username, **kwargs):
    defaults = dict(
        email=f"{username}@x.de", password_hash="h", first_name=username,
        last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _admin(db):
    return _make_user(db, "wh_admin", role=UserRole.ADMIN)


def test_whchange_rejected_for_daily_schedule_user(db, default_tenant):
    """use_daily_schedule=True → 400, KEINE Historie geschrieben."""
    admin = _admin(db)
    emp = _make_user(
        db, "wh_daily", use_daily_schedule=True,
        hours_monday=8.0, hours_tuesday=8.0, hours_wednesday=8.0,
        hours_thursday=8.0, hours_friday=8.0,
    )
    with pytest.raises(HTTPException) as exc:
        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(
                effective_from=date(2026, 1, 1), weekly_hours=20.0,
            ),
            db=db, current_user=admin,
        )
    assert exc.value.status_code == 400
    assert "individuellem Tagesplan" in exc.value.detail
    # Keine WHChange-Zeile persistiert.
    n = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == emp.id).count()
    assert n == 0


def test_whchange_ok_for_normal_user(db, default_tenant):
    """Normaler MA (use_daily_schedule=False) → unverändert ok, Zeile angelegt."""
    admin = _admin(db)
    emp = _make_user(db, "wh_normal")  # use_daily_schedule default False
    result = create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2026, 1, 1), weekly_hours=20.0,
        ),
        db=db, current_user=admin,
    )
    assert float(result.weekly_hours) == 20.0
    n = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == emp.id).count()
    assert n == 1


# ---------------------------------------------------------------------------
# Finding 4 (HIGH, Review 2026-07-14): die Session ist autoflush=False. Ohne ein
# db.flush() nach db.add(change) UND VOR der Most-Recent-Selbstabfrage sieht
# diese Abfrage die gerade hinzugefügte Zeile nicht → user.weekly_hours bleibt
# beim ersten rückwirkenden Antrag unverändert bzw. übernimmt bei einer
# zweiten, überholenden Änderung den VORHERIGEN statt den neuen Wert.
# ---------------------------------------------------------------------------

def test_whchange_first_past_dated_change_updates_weekly_hours(db, default_tenant):
    """Die allererste rückwirkende (effective_from <= heute) Stundenänderung muss
    user.weekly_hours SOFORT auf den neuen Wert setzen."""
    admin = _admin(db)
    emp = _make_user(db, "wh_first", weekly_hours=40.0)
    result = create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2020, 1, 1), weekly_hours=20.0,
        ),
        db=db, current_user=admin,
    )
    assert float(result.weekly_hours) == 20.0
    assert float(emp.weekly_hours) == 20.0


def test_whchange_second_superseding_change_updates_to_new_value(db, default_tenant):
    """Eine zweite, spätere rückwirkende Änderung muss user.weekly_hours auf
    IHREN Wert setzen — nicht auf den der ersten (bereits committeten) Änderung."""
    admin = _admin(db)
    emp = _make_user(db, "wh_second", weekly_hours=40.0)
    create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2020, 1, 1), weekly_hours=20.0,
        ),
        db=db, current_user=admin,
    )
    result = create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2020, 6, 1), weekly_hours=30.0,
        ),
        db=db, current_user=admin,
    )
    assert float(result.weekly_hours) == 30.0
    assert float(emp.weekly_hours) == 30.0
