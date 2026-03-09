# backend/app/schemas/journal.py
from pydantic import BaseModel
from typing import List, Optional


class JournalTimeEntry(BaseModel):
    id: str
    start_time: Optional[str]
    end_time: Optional[str]
    break_minutes: int
    net_hours: float


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
