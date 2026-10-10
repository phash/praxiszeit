"""Spec 2026-10-08, Abschnitt 14 / E67: die eigene Arbeitszeit im Profil."""
# #225: ``date`` aliasieren, damit das Feld namens ``date`` den Typ nicht verdeckt.
from datetime import date as date_type
from typing import Any, List, Optional

from pydantic import BaseModel


class WorkScheduleSnapshot(BaseModel):
    blocks: Optional[Any] = None   # kanonische JSON-Woche, locker gelesen (E29)
    day_targets: List[float]       # Mo–Fr
    weekly_hours: float


class WorkScheduleToday(WorkScheduleSnapshot):
    date: date_type


class WorkScheduleHistoryRow(WorkScheduleSnapshot):
    effective_from: date_type
    effective_until: Optional[date_type] = None


class MyWorkScheduleResponse(BaseModel):
    today: WorkScheduleToday
    history: List[WorkScheduleHistoryRow]
