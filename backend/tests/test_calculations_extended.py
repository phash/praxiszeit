"""Erweiterte Tests für calculation_service (Lücken aus Full Sweep Audit)."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import (
    User, UserRole, TimeEntry, Absence, AbsenceType,
    PublicHoliday, WorkingHoursChange
)
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_user(db, **kwargs):
    """Helper: User erstellen und committen."""
    defaults = dict(
        username="u_default",
        email="u@example.com",
        password_hash="hash",
        first_name="X",
        last_name="Y",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_entry(db, user, d, start_h, end_h, break_min=0):
    """Helper: Zeiteintrag erstellen und committen."""
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        start_time=time(start_h, 0),
        end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ============================================================
# get_weekly_hours_for_date
# ============================================================

def test_weekly_hours_no_history_returns_user_hours(db, test_user):
    """Kein historischer Eintrag → user.weekly_hours wird verwendet."""
    result = calculation_service.get_weekly_hours_for_date(
        db, test_user, date(2026, 3, 10)
    )
    assert result == Decimal('40.0')


def test_weekly_hours_with_history_before_date(db, test_user):
    """Historischer Eintrag vor Datum → historische Stunden."""
    change = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        weekly_hours=20.0,
        effective_from=date(2026, 1, 1),
    )
    db.add(change)
    db.commit()
    result = calculation_service.get_weekly_hours_for_date(
        db, test_user, date(2026, 3, 10)
    )
    assert result == Decimal('20.0')


def test_weekly_hours_with_history_after_date_ignored(db, test_user):
    """Historischer Eintrag NACH Datum → wird ignoriert, user.weekly_hours gilt."""
    change = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        weekly_hours=20.0,
        effective_from=date(2026, 6, 1),
    )
    db.add(change)
    db.commit()
    result = calculation_service.get_weekly_hours_for_date(
        db, test_user, date(2026, 3, 10)
    )
    assert result == Decimal('40.0')


def test_weekly_hours_most_recent_history_wins(db, test_user):
    """Mehrere historische Einträge → der neueste (≤ Datum) gewinnt."""
    change_old = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        weekly_hours=20.0,
        effective_from=date(2026, 1, 1),
    )
    change_new = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        weekly_hours=32.0,
        effective_from=date(2026, 2, 1),
    )
    db.add(change_old)
    db.add(change_new)
    db.commit()
    result = calculation_service.get_weekly_hours_for_date(
        db, test_user, date(2026, 3, 10)
    )
    assert result == Decimal('32.0')


# ============================================================
# get_daily_target_for_date
# ============================================================

def test_daily_target_monday_standard(db, test_user):
    """Montag → 40h/5 = 8h/Tag."""
    monday = date(2026, 3, 9)
    assert monday.weekday() == 0
    result = calculation_service.get_daily_target_for_date(test_user, monday)
    assert result == Decimal('8.00')


def test_daily_target_friday_standard(db, test_user):
    """Freitag → 8h/Tag."""
    friday = date(2026, 3, 13)
    assert friday.weekday() == 4
    result = calculation_service.get_daily_target_for_date(test_user, friday)
    assert result == Decimal('8.00')


def test_daily_target_saturday_is_zero(db, test_user):
    """Samstag → 0."""
    saturday = date(2026, 3, 14)
    assert saturday.weekday() == 5
    result = calculation_service.get_daily_target_for_date(test_user, saturday)
    assert result == Decimal('0')


def test_daily_target_sunday_is_zero(db, test_user):
    """Sonntag → 0."""
    sunday = date(2026, 3, 15)
    assert sunday.weekday() == 6
    result = calculation_service.get_daily_target_for_date(test_user, sunday)
    assert result == Decimal('0')


def test_daily_target_with_daily_schedule_monday(db):
    """use_daily_schedule=True → Montag-spezifische Stunden."""
    user = _make_user(
        db,
        username="sched_user",
        email="sched@example.com",
        use_daily_schedule=True,
        hours_monday=4.0,
        hours_tuesday=6.0,
        hours_wednesday=8.0,
        hours_thursday=6.0,
        hours_friday=4.0,
    )
    monday = date(2026, 3, 9)
    result = calculation_service.get_daily_target_for_date(user, monday)
    assert result == Decimal('4.00')


def test_daily_target_with_daily_schedule_wednesday(db):
    """use_daily_schedule=True → Mittwoch-spezifische Stunden."""
    user = _make_user(
        db,
        username="sched_user2",
        email="sched2@example.com",
        use_daily_schedule=True,
        hours_monday=4.0,
        hours_tuesday=6.0,
        hours_wednesday=8.0,
        hours_thursday=6.0,
        hours_friday=4.0,
    )
    wednesday = date(2026, 3, 11)
    result = calculation_service.get_daily_target_for_date(user, wednesday)
    assert result == Decimal('8.00')


# ============================================================
# get_working_days_in_month
# ============================================================

def test_working_days_january_2026(db):
    """Januar 2026 → 22 Werktage (1. Jan ist Donnerstag)."""
    result = calculation_service.get_working_days_in_month(db, 2026, 1)
    assert result == 22


def test_working_days_february_2026(db):
    """Februar 2026 → 20 Werktage (28 Tage, 4 Sa + 4 So)."""
    result = calculation_service.get_working_days_in_month(db, 2026, 2)
    assert result == 20


def test_working_days_does_not_deduct_holidays(db):
    """get_working_days_in_month ignoriert Feiertage (by design – nur Wochenenden)."""
    h = PublicHoliday(date=date(2026, 1, 1), name="Neujahr", year=2026, tenant_id=DEFAULT_TENANT_ID)
    db.add(h)
    db.commit()
    result = calculation_service.get_working_days_in_month(db, 2026, 1)
    assert result == 22  # Unverändert – Funktion berücksichtigt Feiertage nicht


# ============================================================
# get_monthly_target
# ============================================================

def test_monthly_target_with_holiday_reduces_target(db, test_user):
    """Feiertag an Werktag → Soll wird um 8h reduziert."""
    target_without = calculation_service.get_monthly_target(db, test_user, 2026, 1)
    # 01.01.2026 ist Donnerstag (Werktag)
    h = PublicHoliday(date=date(2026, 1, 1), name="Neujahr", year=2026, tenant_id=DEFAULT_TENANT_ID)
    db.add(h)
    db.commit()
    target_with = calculation_service.get_monthly_target(db, test_user, 2026, 1)
    assert target_with == target_without - Decimal('8.00')


def test_monthly_target_with_vacation_reduces(db, test_user):
    """VACATION-Abwesenheit reduziert Soll."""
    target_without = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    absence = Absence(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=date(2026, 3, 10),  # Dienstag
        type=AbsenceType.VACATION,
        hours=8.0,
    )
    db.add(absence)
    db.commit()
    target_with = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    assert target_with == target_without - Decimal('8.00')


def test_monthly_target_training_does_not_reduce(db, test_user):
    """TRAINING-Abwesenheit reduziert Soll NICHT (gilt als gearbeitet)."""
    target_without = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    absence = Absence(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=date(2026, 3, 10),
        type=AbsenceType.TRAINING,
        hours=8.0,
    )
    db.add(absence)
    db.commit()
    target_with = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    assert target_with == target_without


def test_monthly_target_with_overtime_absence_reduces(db, test_user):
    """OVERTIME-Abwesenheit reduziert Soll."""
    target_without = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    absence = Absence(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=date(2026, 3, 10),
        type=AbsenceType.OVERTIME,
        hours=8.0,
    )
    db.add(absence)
    db.commit()
    target_with = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    assert target_with == target_without - Decimal('8.00')


# ============================================================
# get_vacation_account – Pro-Rata
# ============================================================

def test_vacation_account_first_work_day_reduces_budget(db):
    """first_work_day = 1. Juli 2026 → 6/12 Budget."""
    user = _make_user(
        db,
        username="new_emp",
        email="new@example.com",
        vacation_days=24,
        first_work_day=date(2026, 7, 1),
    )
    result = calculation_service.get_vacation_account(db, user, 2026)
    # 1. Juli: Monat hat 31 Tage, days_remaining=31, months_remaining=5+31/31=6.0
    # budget_days = 24 * 6.0 / 12 = 12.0
    assert result["budget_days"] == 12.0


def test_vacation_account_last_work_day_reduces_budget(db):
    """last_work_day = 30. Juni 2026 → 6/12 Budget."""
    user = _make_user(
        db,
        username="leaving_emp",
        email="leaving@example.com",
        vacation_days=24,
        last_work_day=date(2026, 6, 30),
    )
    result = calculation_service.get_vacation_account(db, user, 2026)
    # 30. Juni: Monat hat 30 Tage, days_worked=30, months_worked=5+30/30=6.0
    # budget_days = 24 * 6.0 / 12 = 12.0
    assert result["budget_days"] == 12.0


def test_vacation_account_both_set_takes_minimum(db):
    """Beide gesetzt → Minimum beider Berechnungen."""
    user = _make_user(
        db,
        username="both_emp",
        email="both@example.com",
        vacation_days=24,
        first_work_day=date(2026, 7, 1),   # → 12.0
        last_work_day=date(2026, 8, 31),   # → 24*8/12 = 16.0 → min(12,16)=12
    )
    result = calculation_service.get_vacation_account(db, user, 2026)
    assert result["budget_days"] == 12.0


def test_vacation_account_mid_month_day_accurate(db):
    """Tagesgenaue Berechnung: 15. März < 1. März in Budget."""
    user_1st = _make_user(
        db,
        username="mar1",
        email="mar1@example.com",
        vacation_days=12,
        first_work_day=date(2026, 3, 1),
    )
    user_15th = _make_user(
        db,
        username="mar15",
        email="mar15@example.com",
        vacation_days=12,
        first_work_day=date(2026, 3, 15),
    )
    result_1 = calculation_service.get_vacation_account(db, user_1st, 2026)
    result_15 = calculation_service.get_vacation_account(db, user_15th, 2026)
    assert result_15["budget_days"] < result_1["budget_days"]


# ============================================================
# count_workdays
# ============================================================

def test_count_workdays_simple_week(db):
    """Mo-Fr ohne Feiertage → 5 Werktage."""
    result = calculation_service.count_workdays(db, date(2026, 3, 9), date(2026, 3, 13))
    assert result == 5


def test_count_workdays_excludes_holiday(db):
    """Feiertag im Bereich → wird abgezogen."""
    h = PublicHoliday(date=date(2026, 3, 11), name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID)
    db.add(h)
    db.commit()
    result = calculation_service.count_workdays(db, date(2026, 3, 9), date(2026, 3, 13))
    assert result == 4


def test_count_workdays_excludes_weekends(db):
    """Wochenende wird ausgeschlossen."""
    # Sa 14.03. + So 15.03. + Mo 16.03. → nur Montag zählt
    result = calculation_service.count_workdays(db, date(2026, 3, 14), date(2026, 3, 16))
    assert result == 1


def test_count_workdays_cross_month(db):
    """Monatsübergreifend: Mo 30.03.–Fr 03.04. → 5 Werktage."""
    result = calculation_service.count_workdays(db, date(2026, 3, 30), date(2026, 4, 3))
    assert result == 5


# ============================================================
# get_overtime_account
# ============================================================

def test_overtime_account_no_entries_returns_zero(db, test_user):
    """Keine Einträge → 0.00."""
    result = calculation_service.get_overtime_account(db, test_user, 2026, 3)
    assert result == Decimal('0.00')


def test_overtime_account_cumulates_across_months(db, test_user):
    """Einträge in mehreren Monaten → kumulierter Saldo."""
    _make_entry(db, test_user, date(2026, 1, 9), 8, 18)   # 10h Ist
    _make_entry(db, test_user, date(2026, 2, 9), 8, 16)   # 8h Ist
    result = calculation_service.get_overtime_account(db, test_user, 2026, 2)
    # Two months with large targets (176h Jan + 160h Feb) vs. small actuals (10h + 8h)
    # Key: result must be negative AND cumulate across both months
    assert result < Decimal('0')
    # Verify both months are included: if only Jan were counted, result would be > -175
    assert result < Decimal('-175')
