"""#205: tagebasierter Urlaubsverbrauch via persistiertem half_day.

Part 1 — tracked: voller Tag bleibt 1,0, auch nach rueckwirkender
WorkingHoursChange (frueher Stunden ÷ live-Tagessoll -> Drift).
Part 2 — untracked: Halbtag zaehlt 0,5 (passend zum 0,5-Vorab-Budgetcheck).
Legacy-Rows (half_day=None, vor dem Feld) behalten die alte Stundenlogik.
"""
from datetime import date

from app.models import User, UserRole, Absence, AbsenceType, WorkingHoursChange
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _user(db, track_hours=True, weekly_hours=40.0, username="u205"):
    u = User(
        username=username, email=f"{username}@example.de", password_hash="h",
        first_name="A", last_name="B", role=UserRole.EMPLOYEE,
        weekly_hours=weekly_hours, vacation_days=30, work_days_per_week=5,
        track_hours=track_hours, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _vac(db, u, d, hours, half_day):
    a = Absence(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        type=AbsenceType.VACATION, hours=hours, half_day=half_day,
    )
    db.add(a); db.commit()
    return a


# 2026-03-10 / -11 sind Werktage (Di/Mi) — wie in test_vacation_account_untracked.

def test_part1_full_day_stable_after_retroactive_whchange(db, default_tenant):
    """Voller Urlaubstag (half_day=False) bleibt 1,0 — auch wenn eine
    rueckwirkende WorkingHoursChange das Tagessoll halbiert (frueher 2,0)."""
    u = _user(db)  # 40h/5 = 8h/Tag
    _vac(db, u, date(2026, 3, 10), hours=8.0, half_day=False)
    assert calculation_service.get_vacation_account(db, u, 2026)["used_days"] == 1.0

    db.add(WorkingHoursChange(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID,
        weekly_hours=20.0, effective_from=date(2026, 3, 1),
    ))
    db.commit()
    # tagebasiert -> stabil bei 1,0 (frueher 8/4 = 2,0)
    assert calculation_service.get_vacation_account(db, u, 2026)["used_days"] == 1.0


def test_tracked_half_day_counts_half(db, default_tenant):
    u = _user(db)
    _vac(db, u, date(2026, 3, 10), hours=4.0, half_day=True)
    assert calculation_service.get_vacation_account(db, u, 2026)["used_days"] == 0.5


def test_tracked_legacy_null_uses_hours_based_no_regression(db, default_tenant):
    """Legacy-Row (half_day=None) -> weiter stundenbasiert (8/8 = 1,0)."""
    u = _user(db)
    _vac(db, u, date(2026, 3, 10), hours=8.0, half_day=None)
    assert calculation_service.get_vacation_account(db, u, 2026)["used_days"] == 1.0


def test_part2_untracked_half_day_counts_half(db, default_tenant):
    """Untracked (track_hours=False) Halbtag -> 0,5 statt 1,0 (Vorab-Check-Konsistenz)."""
    u = _user(db, track_hours=False)
    _vac(db, u, date(2026, 3, 10), hours=0.0, half_day=True)
    assert calculation_service.get_vacation_account(db, u, 2026)["used_days"] == 0.5


def test_untracked_full_and_legacy_count_one_each(db, default_tenant):
    u = _user(db, track_hours=False)
    _vac(db, u, date(2026, 3, 10), hours=0.0, half_day=False)  # neuer Voll-Tag
    _vac(db, u, date(2026, 3, 11), hours=0.0, half_day=None)   # Legacy
    assert calculation_service.get_vacation_account(db, u, 2026)["used_days"] == 2.0
