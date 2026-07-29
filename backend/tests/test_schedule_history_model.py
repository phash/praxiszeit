"""#431: die WorkingHoursChange-Zeile ist ein vollstaendiger Vertrags-Snapshot."""
from datetime import date
from decimal import Decimal

from app.models import WorkingHoursChange


def test_row_carries_full_snapshot(db, test_user):
    row = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1),
        weekly_hours=Decimal("17.0"),
        use_daily_schedule=True,
        hours_monday=Decimal("8.0"),
        hours_tuesday=Decimal("5.0"),
        hours_wednesday=Decimal("4.0"),
        hours_thursday=None,
        hours_friday=None,
        work_days_per_week=3,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.use_daily_schedule is True
    assert Decimal(str(row.hours_monday)) == Decimal("8.0")
    assert row.hours_thursday is None
    assert row.work_days_per_week == 3


def test_defaults_are_weekly_mode(db, test_user):
    """Eine Zeile ohne Tagesangaben ist eine gleichmaessige Zeile — das ist der
    Zustand aller Bestandszeilen von Nicht-Tagesplan-Mitarbeitenden."""
    row = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1),
        weekly_hours=Decimal("40.0"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.use_daily_schedule is False
    assert row.hours_monday is None
    assert row.work_days_per_week is None
