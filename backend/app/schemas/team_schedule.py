"""1.21 Teamübersicht der Arbeitszeiten (``GET /api/admin/team-schedule``)."""
from datetime import date
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.user import ScheduleTodayResponse


class TeamScheduleNextChange(BaseModel):
    """Die nächste Arbeitszeit-Änderung NACH dem angefragten Datum."""
    effective_from: date
    blocks: Optional[Any] = None


class TeamScheduleRow(BaseModel):
    """Eine Person mit dem zum Datum gültigen Vertrags-Snapshot.

    ``blocks`` locker typisiert wie ``UserResponse.work_blocks_today`` (E29);
    ``legacy`` = Altfenster aus Migration 073 (kappt, treibt kein Soll);
    ``schedule`` = Anzeigewerte desselben Snapshots — der Dialog „Arbeitszeit
    anpassen…" braucht sie als Rückfall, solange es keinen Verlauf gibt."""
    user_id: UUID
    first_name: str
    last_name: str
    department: Optional[str] = None
    calendar_color: str
    track_hours: bool
    use_fixed_monthly_target: bool = False
    blocks: Optional[Any] = None
    legacy: bool = False
    schedule: ScheduleTodayResponse
    next_change: Optional[TeamScheduleNextChange] = None
