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
    milog_warnings: List[str] = []  # #377 §2 Abs.2 MiLoG (self-scoped; leer wenn Flag aus)


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


class AdminUserOverview(BaseModel):
    """#194: per-user vacation account + YTD overtime for the admin user list.

    Bulk-served by GET /api/admin/users-overview so the frontend needs a
    single request instead of the former per-user N+1 vacation fetch.
    """
    user_id: str
    first_name: str
    last_name: str
    track_hours: bool
    vacation: VacationAccount
    overtime: YtdOvertime
    child_sick_used: float = 0.0   # #376 §45 SGB V: verbrauchte Kind-krank-Tage im Jahr
    child_sick_cap: int = 15       # #376: persönlicher Cap (MA-Feld → Tenant-Default → 15)
    milog_warnings: List[str] = [] # #377 §2 Abs.2 MiLoG (leer wenn Flag aus / nichts überschritten)


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
    vacation_used_days: float   # Tagesprinzip: Stunden ÷ Tagessoll (für die Anzeige)
    sick_hours: float
    sick_days: float            # 0 ohne include_health_data (DSGVO Art. 9)
    exempt_from_arbzg: bool = False  # #159: leitende Angestellte (§18) — Filter im Dashboard-Schnitt
    track_hours: bool = True    # Finding 14: #191-untracked MA aus "Ø Saldo" ausschließbar


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
    paid_leave_days: float = 0.0
    overtime_year: float
    total_days: float
