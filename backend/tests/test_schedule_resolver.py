"""#431: der Snapshot-Resolver — Query-Pfad, Preload-Pfad, Rueckfall."""
from datetime import date
from decimal import Decimal

from app.models import WorkingHoursChange
from app.services import calculation_service as cs


def _row(user, day, **kw):
    return WorkingHoursChange(
        user_id=user.id, tenant_id=user.tenant_id, effective_from=day, **kw)


def test_fallback_to_user_when_no_history(db, test_user):
    test_user.weekly_hours = Decimal("40.0")
    test_user.work_days_per_week = 5
    test_user.use_daily_schedule = False
    db.commit()

    s = cs.get_schedule_for_date(db, test_user, date(2026, 5, 4))

    assert s.weekly_hours == Decimal("40.0")
    assert s.use_daily_schedule is False
    assert s.work_days_per_week == 5


def test_resolves_day_plan_snapshot(db, test_user):
    db.add(_row(
        test_user, date(2026, 3, 1),
        weekly_hours=Decimal("17.0"), use_daily_schedule=True,
        hours_monday=Decimal("8.0"), hours_tuesday=Decimal("5.0"),
        hours_wednesday=Decimal("4.0"), work_days_per_week=3,
    ))
    db.commit()

    before = cs.get_schedule_for_date(db, test_user, date(2026, 2, 28))
    after = cs.get_schedule_for_date(db, test_user, date(2026, 3, 2))

    assert before.use_daily_schedule is False
    assert after.use_daily_schedule is True
    assert after.day_hours[0] == Decimal("8.0")
    assert after.day_hours[3] is None
    assert after.work_days_per_week == 3


def test_preload_path_matches_query_path(db, test_user):
    db.add(_row(test_user, date(2026, 1, 1), weekly_hours=Decimal("40.0")))
    db.add(_row(
        test_user, date(2026, 3, 1), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"), work_days_per_week=3))
    db.commit()
    preload = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == test_user.id).all()

    for d in (date(2026, 1, 15), date(2026, 2, 28), date(2026, 3, 1), date(2026, 12, 31)):
        assert cs.get_schedule_for_date(db, test_user, d) == \
               cs.get_schedule_for_date(db, test_user, d, wh_changes=preload)


def test_weekly_hours_helper_still_matches_resolver(db, test_user):
    """get_weekly_hours_for_date bleibt die oeffentliche Wochenstunden-Quelle und
    darf nie vom Resolver abweichen."""
    db.add(_row(test_user, date(2026, 3, 1), weekly_hours=Decimal("17.0")))
    db.commit()

    for d in (date(2026, 2, 1), date(2026, 3, 1), date(2026, 6, 1)):
        assert cs.get_weekly_hours_for_date(db, test_user, d) == \
               cs.get_schedule_for_date(db, test_user, d).weekly_hours


def test_work_days_falls_back_when_row_has_none(db, test_user):
    """Bestandszeilen ohne Backfill (theoretisch) fallen auf den User-Wert."""
    test_user.work_days_per_week = 4
    db.add(_row(test_user, date(2026, 3, 1), weekly_hours=Decimal("20.0")))
    db.commit()

    s = cs.get_schedule_for_date(db, test_user, date(2026, 4, 1))
    assert s.work_days_per_week == 4
