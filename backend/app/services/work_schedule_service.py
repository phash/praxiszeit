"""Spec 2026-10-08, Abschnitt 14 / E67 / P12: die eigene Arbeitszeit — heute
gültige Blöcke und Verlauf. Datumsaufgelöst über den Vertrags-Snapshot
(``calculation_service.get_schedule_for_date``), nie aus ``users.work_blocks``
direkt; ohne den Verwaltungsfreitext ``note`` (der steht im Art.-15-Export)."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import User, WorkingHoursChange
from app.services import calculation_service


def _snapshot(db: Session, user: User, d: date, wh_changes) -> dict:
    schedule = calculation_service.get_schedule_for_date(db, user, d, wh_changes)
    monday = d - timedelta(days=d.weekday())
    return {
        "blocks": calculation_service.get_blocks_json_for_date(db, user, d, wh_changes),
        "day_targets": [
            float(calculation_service.get_daily_target_for_date(user, monday + timedelta(days=i), schedule))
            for i in range(5)
        ],
        "weekly_hours": float(schedule.weekly_hours),
    }


def build_my_work_schedule(db: Session, user: User, on_date: date) -> dict:
    rows = (
        db.query(WorkingHoursChange)
        .filter(
            WorkingHoursChange.user_id == user.id,
            WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
        )
        .order_by(WorkingHoursChange.effective_from)
        .all()
    )
    history = []
    for i, row in enumerate(rows):
        following = rows[i + 1].effective_from if i + 1 < len(rows) else None
        history.append({
            "effective_from": row.effective_from,
            "effective_until": following - timedelta(days=1) if following else None,
            **_snapshot(db, user, row.effective_from, rows),
        })
    # #463: dieselbe Bedingung wie ``journal_service.fixed_mode`` und
    # ``get_range_target`` — das Flag allein genügt nicht, ohne
    # ``agreed_monthly_hours`` gibt es kein festes Soll.
    fixed_mode = bool(
        getattr(user, "use_fixed_monthly_target", False)
        and getattr(user, "agreed_monthly_hours", None)
    )
    return {
        "today": {"date": on_date, **_snapshot(db, user, on_date, rows)},
        "history": history,
        "track_hours": bool(getattr(user, "track_hours", True)),
        "fixed_monthly_hours": float(user.agreed_monthly_hours) if fixed_mode else None,
    }
