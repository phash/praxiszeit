"""#431: das Tagessoll folgt dem historischen Tagesplan, nicht dem aktuellen."""
from datetime import date
from decimal import Decimal

from app.models import WorkingHoursChange
from app.services import calculation_service as cs


def test_day_plan_target_is_date_aware(db, test_user):
    """Kern von #431: ein Mittwoch im Februar rechnet mit dem Februar-Plan,
    obwohl der Mitarbeiter heute einen anderen Plan hat."""
    test_user.use_daily_schedule = True
    test_user.hours_monday = Decimal("4.0")
    test_user.hours_wednesday = Decimal("2.0")
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_tuesday=Decimal("5.0"), hours_wednesday=Decimal("4.0"),
        work_days_per_week=3,
    ))
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1), weekly_hours=Decimal("6.0"),
        use_daily_schedule=True, hours_monday=Decimal("4.0"),
        hours_wednesday=Decimal("2.0"), work_days_per_week=2,
    ))
    db.commit()

    feb_wed = date(2026, 2, 4)   # Mittwoch
    apr_wed = date(2026, 4, 1)   # Mittwoch
    assert cs.get_daily_target_for_date(
        test_user, feb_wed, cs.get_schedule_for_date(db, test_user, feb_wed)
    ) == Decimal("4.00")
    assert cs.get_daily_target_for_date(
        test_user, apr_wed, cs.get_schedule_for_date(db, test_user, apr_wed)
    ) == Decimal("2.00")


def test_weekly_mode_uses_historical_work_days(db, test_user):
    """Arbeitstage sind ebenfalls historisiert: 20 h auf 4 Tage = 5 h/Tag,
    danach 20 h auf 5 Tage = 4 h/Tag."""
    test_user.use_daily_schedule = False
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("20.0"),
        work_days_per_week=4,
    ))
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 6, 1), weekly_hours=Decimal("20.0"),
        work_days_per_week=5,
    ))
    db.commit()

    d1, d2 = date(2026, 2, 3), date(2026, 7, 7)
    assert cs.get_daily_target_for_date(
        test_user, d1, cs.get_schedule_for_date(db, test_user, d1)) == Decimal("5.00")
    assert cs.get_daily_target_for_date(
        test_user, d2, cs.get_schedule_for_date(db, test_user, d2)) == Decimal("4.00")


def test_monthly_target_follows_historical_day_plan(db, test_user):
    """Das ist der eigentliche #431-Nutzen: das MONATS-Soll (§16-Beleg) rechnet
    fuer einen Tagesplan-MA mit dem Plan, der im jeweiligen Monat galt.

    Die reinen Leaf-Tests oben wuerden auch dann noch gruen sein, wenn eine
    Tagesschleife den Snapshot zwar uebergibt, ihn aber am falschen Datum
    aufloest — dieser Test bindet die Kette bis get_monthly_target zusammen.
    """
    test_user.use_daily_schedule = True
    test_user.hours_monday = Decimal("4.0")
    test_user.hours_wednesday = Decimal("2.0")
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_tuesday=Decimal("5.0"), hours_wednesday=Decimal("4.0"),
        work_days_per_week=3,
    ))
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1), weekly_hours=Decimal("6.0"),
        use_daily_schedule=True, hours_monday=Decimal("4.0"),
        hours_wednesday=Decimal("2.0"), work_days_per_week=2,
    ))
    db.commit()

    # Februar 2026: 4 Mo, 4 Di, 4 Mi → 4×8 + 4×5 + 4×4 = 68 h (alter Plan).
    # Mit dem HEUTIGEN Plan waeren es 4×4 + 4×2 = 24 h gewesen.
    assert cs.get_monthly_target(db, test_user, 2026, 2) == Decimal("68.00")
    # April 2026: 4 Mo, 5 Mi (Di faellt weg) → 4×4 + 5×2 = 26 h (neuer Plan).
    assert cs.get_monthly_target(db, test_user, 2026, 4) == Decimal("26.00")


def test_untracked_user_still_zero(db, test_user):
    test_user.track_hours = False
    db.commit()
    d = date(2026, 4, 1)
    assert cs.get_daily_target_for_date(
        test_user, d, cs.get_schedule_for_date(db, test_user, d)) == Decimal("0")
