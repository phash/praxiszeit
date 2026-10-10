# backend/app/schemas/journal.py
from pydantic import BaseModel
from typing import List, Optional


class JournalTimeEntry(BaseModel):
    id: str
    start_time: Optional[str]
    end_time: Optional[str]
    break_minutes: int
    net_hours: float
    # #485: Bis 1.19.2 fehlten diese Felder hier — die Rohstempel-Zeile des
    # Monatsjournals (RawStampNote) bekam nie einen Wert, und das Bearbeiten-
    # Formular konnte den §10-Grund nicht vorbelegen.
    raw_start_time: Optional[str] = None
    raw_end_time: Optional[str] = None
    sunday_exception_reason: Optional[str] = None
    # Spec 2026-10-08 (13.2, P18, P19): ohne diese Felder filterte das
    # response_model sie still weg (CLAUDE.md #485).
    uncredited_minutes: int = 0
    not_credited_minutes: int = 0
    credit_override: bool = False
    auto_closed: bool = False


class JournalAbsence(BaseModel):
    id: str
    type: str
    hours: float


class JournalDay(BaseModel):
    date: str
    weekday: str
    type: str
    is_holiday: bool
    holiday_name: Optional[str]
    time_entries: List[JournalTimeEntry]
    absences: List[JournalAbsence]
    actual_hours: float
    target_hours: float
    balance: float


class JournalMonthlySummary(BaseModel):
    actual_hours: float
    target_hours: float
    balance: float
    # Spec 13.2: Σ not_credited_minutes (Lücke + Hülle) — Zeile
    # „Anwesenheit nicht angerechnet" im Journal.
    not_credited_minutes_total: int = 0


class JournalUser(BaseModel):
    id: str
    first_name: str
    last_name: str


class JournalResponse(BaseModel):
    user: JournalUser
    year: int
    month: int
    days: List[JournalDay]
    monthly_summary: JournalMonthlySummary
    yearly_overtime: float
    # #463: Im festen Monats-Soll (#377 Baustein 2b) hat ein Tages-Soll keine
    # Bedeutung — es gibt keins. ``target_hours``/``balance`` der TAGESzeilen
    # tragen dort die geplante Anwesenheit, nicht eine Zerlegung des flachen
    # Monatswertes (siehe journal_service). Ohne dieses Kennzeichen kann die
    # Oberflaeche das nicht unterscheiden und zeigt Zahlen ohne definierte
    # Bedeutung — der Melder las daraus einen Rechenfehler.
    use_fixed_monthly_target: bool = False
