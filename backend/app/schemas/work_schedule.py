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
    # Review Task 10: der Modus der Person, damit die Karte nichts „Tagessoll" nennt,
    # was keins ist. ``track_hours=False`` (#191): kein Soll, keine Kappung (E35/E63).
    # ``fixed_monthly_hours`` (#377 Baustein 2b): das feste Monats-Soll; die Tageswerte
    # sind dann nur geplante Anwesenheit (wie im Monatsjournal, #463). Beide Felder
    # sind heutige Werte der User-Zeile — sie sind nicht historisiert.
    track_hours: bool = True
    fixed_monthly_hours: Optional[float] = None
