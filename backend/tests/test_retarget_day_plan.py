"""#431: Rueckrechnung gebuchter Abwesenheits-Stunden bei Tagesplan-Aenderung."""
from datetime import date
from decimal import Decimal

from app.models import Absence, AbsenceType, WorkingHoursChange
from app.services import calculation_service as cs


def _absence(user, day, hours):
    return Absence(
        user_id=user.id, tenant_id=user.tenant_id, date=day,
        type=AbsenceType.SICK, hours=hours, half_day=False)


def test_only_changed_weekday_is_retargeted(db, test_user):
    test_user.use_daily_schedule = True
    test_user.track_hours = True
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("12.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_wednesday=Decimal("4.0"), work_days_per_week=2))
    mon, wed = date(2026, 3, 2), date(2026, 3, 4)
    db.add(_absence(test_user, mon, 8.0))
    db.add(_absence(test_user, wed, 4.0))
    db.commit()

    # Nur der Mittwoch aendert sich: 4 h -> 6 h.
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1), weekly_hours=Decimal("14.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_wednesday=Decimal("6.0"), work_days_per_week=2))
    db.commit()

    changed = cs.retarget_absence_hours(db, test_user, date(2026, 3, 1), date(2026, 3, 31), old_full_target_by_date={})
    db.commit()

    rows = {a.date: Decimal(str(a.hours)) for a in db.query(Absence).filter(
        Absence.user_id == test_user.id).all()}
    assert len(changed) == 1
    assert rows[mon] == Decimal("8.00")   # unveraendert
    assert rows[wed] == Decimal("6.00")   # nachgezogen


def test_free_weekday_is_skipped_not_zeroed(db, test_user):
    """Ein Tag ohne Soll im Plan wird fuer Urlaub uebersprungen, nicht auf 0
    gesetzt — dessen ``hours`` tragen kein Saldo."""
    test_user.use_daily_schedule = True
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("8.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"), work_days_per_week=1))
    fri = date(2026, 3, 6)
    vacation = _absence(test_user, fri, 3.0)
    vacation.type = AbsenceType.VACATION
    db.add(vacation)
    db.commit()

    changed = cs.retarget_absence_hours(db, test_user, date(2026, 3, 1), date(2026, 3, 31), old_full_target_by_date={})
    row = db.query(Absence).filter(Absence.date == fri).first()

    assert len(changed) == 0
    assert Decimal(str(row.hours)) == Decimal("3.0")


def test_free_weekday_zeroes_the_ist_credit(db, test_user):
    """Gesamtreview 1.20 (Fund 4): Krank/Fortbildung an einem Tag ohne Soll —
    kein Soll, keine Gutschrift. Bis dahin blieb die Zeile wie Urlaub stehen,
    und ``credit_day_weight`` (Wochentag = 1,0) schrieb sie dem Ist gut."""
    test_user.use_daily_schedule = True
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("8.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"), work_days_per_week=1))
    fri = date(2026, 3, 6)
    db.add(_absence(test_user, fri, 3.0))
    db.commit()

    changed = cs.retarget_absence_hours(db, test_user, date(2026, 3, 1), date(2026, 3, 31), old_full_target_by_date={})
    db.commit()
    row = db.query(Absence).filter(Absence.date == fri).first()

    assert [(c.date, c.old_hours, c.new_hours, c.f1_clamped, c.credit_reduction) for c in changed] == [
        (fri, Decimal("3.00"), Decimal("0.00"), False, False)]
    assert Decimal(str(row.hours)) == Decimal("0")
    assert cs.get_range_actual(db, test_user, fri, fri) - cs.get_range_target(db, test_user, fri, fri) == 0
    # Idempotent: ein zweiter Lauf findet nichts mehr.
    assert cs.retarget_absence_hours(db, test_user, date(2026, 3, 1), date(2026, 3, 31), old_full_target_by_date={}) == []
