"""1.21 Teamübersicht der Arbeitszeiten: wer arbeitet laut Vertrag wann.

Rein lesend. Geändert wird eine Arbeitszeit ausschließlich über
``POST /api/admin/users/{id}/working-hours-changes`` (Stichtag, Vorschau,
Verkürzungsschutz) — die Übersicht öffnet dafür denselben Dialog."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import require_admin
from app.models import User, WorkingHoursChange
from app.schemas.team_schedule import TeamScheduleNextChange, TeamScheduleRow
from app.services import calculation_service, work_blocks_service
from app.services.timezone_service import today_local

router = APIRouter(prefix="/api/admin", tags=["admin-team-schedule"], dependencies=[Depends(require_admin)])


@router.get("/team-schedule", response_model=List[TeamScheduleRow])
def team_schedule(
    on_date: Optional[date] = Query(None, alias="date", description="Stand am (YYYY-MM-DD), Standard heute"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Aktive, sichtbare Personen des Mandanten mit dem zu ``date`` gültigen
    Snapshot (``get_schedule_for_date``) und der nächsten späteren Änderung.
    EIN Preload der Verlaufszeilen (Muster #449). F-026: Tenant-Filter."""
    on_date = on_date or today_local()
    users = db.query(User).filter(
        User.tenant_id == current_user.tenant_id,  # F-026
        User.is_active == True,  # noqa: E712
        User.is_hidden == False,  # noqa: E712
    ).order_by(User.last_name, User.first_name).all()
    by_user: dict = {}
    if users:
        for row in db.query(WorkingHoursChange).filter(
            WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
            WorkingHoursChange.user_id.in_([u.id for u in users]),
        ).all():
            by_user.setdefault(row.user_id, []).append(row)

    rows = []
    for user in users:
        changes = by_user.get(user.id, [])
        schedule = calculation_service.get_schedule_for_date(db, user, on_date, changes)
        later = [c for c in changes if c.effective_from > on_date]
        nxt = min(later, key=lambda c: c.effective_from) if later else None
        next_change = None
        if nxt is not None:
            nxt_schedule = calculation_service.get_schedule_for_date(db, user, nxt.effective_from, changes)
            next_change = TeamScheduleNextChange(
                effective_from=nxt.effective_from,
                blocks=work_blocks_service.week_blocks_to_json(nxt_schedule.blocks, nxt_schedule.block_pauses),
            )
        rows.append(TeamScheduleRow(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            department=user.department,
            calendar_color=user.calendar_color,
            track_hours=bool(user.track_hours),
            use_fixed_monthly_target=bool(getattr(user, "use_fixed_monthly_target", False)),
            blocks=work_blocks_service.week_blocks_to_json(schedule.blocks, schedule.block_pauses),
            legacy=schedule.block_pauses is not None and any(p is None for p in schedule.block_pauses),
            schedule=calculation_service.schedule_display_json(schedule),
            next_change=next_change,
        ))
    return rows
