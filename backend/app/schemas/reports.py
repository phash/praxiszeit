from pydantic import BaseModel, ConfigDict
from datetime import date
from decimal import Decimal
from typing import List, Optional


class MonthlyDashboard(BaseModel):
    """Dashboard data for current month."""
    year: int
    month: int
    target_hours: float
    actual_hours: float
    balance: float


class OvertimeHistory(BaseModel):
    """Overtime history by month."""
    year: int
    month: int
    target: float
    actual: float
    balance: float
    cumulative: float


class OvertimeAccount(BaseModel):
    """Complete overtime account."""
    current_balance: float
    history: List[OvertimeHistory]


class YtdOvertime(BaseModel):
    """Year-to-date overtime summary (Jan 1 to today)."""
    year: int
    target_hours: float
    actual_hours: float
    overtime: float
    carryover_hours: float = 0.0


class VacationAccount(BaseModel):
    """Vacation account for a year."""
    year: int
    budget_hours: float
    budget_days: float
    used_hours: float
    used_days: float
    remaining_hours: float
    remaining_days: float
    # Year-end warning info
    carryover_deadline: Optional[date] = None  # Deadline to use remaining vacation
    has_carryover_warning: bool = False  # True if remaining vacation at year end


class EmployeeMonthlyReport(BaseModel):
    """Monthly report for a single employee."""
    user_id: str
    first_name: str
    last_name: str
    weekly_hours: float
    target_hours: float
    actual_hours: float
    balance: float
    overtime_cumulative: float
    vacation_used_hours: float
    sick_hours: float


class PublicHolidayResponse(BaseModel):
    """Public holiday response."""
    model_config = ConfigDict(from_attributes=True)

    date: date
    name: str
    year: int


class MissingBookingEntry(BaseModel):
    """A single missing or incomplete booking."""
    date: date
    type: str  # "open" (end_time NULL) or "missing" (no entry on workday)
    start_time: Optional[str] = None  # For open entries

class MissingBookings(BaseModel):
    """Missing bookings for a single user."""
    user_id: str
    first_name: str
    last_name: str
    entries: List[MissingBookingEntry]

class EmployeeYearlyAbsences(BaseModel):
    """Yearly absence summary for a single employee."""
    user_id: str
    first_name: str
    last_name: str
    vacation_days: float
    remaining_vacation_days: float
    sick_days: float
    training_days: float
    overtime_comp_days: float = 0.0
    other_days: float
    overtime_year: float
    total_days: float
