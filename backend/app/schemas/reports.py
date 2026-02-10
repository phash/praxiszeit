from pydantic import BaseModel
from datetime import date
from decimal import Decimal
from typing import List


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


class VacationAccount(BaseModel):
    """Vacation account for a year."""
    year: int
    budget_hours: float
    budget_days: int
    used_hours: float
    used_days: float
    remaining_hours: float
    remaining_days: float


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
    date: date
    name: str
    year: int

    class Config:
        from_attributes = True


class EmployeeYearlyAbsences(BaseModel):
    """Yearly absence summary for a single employee."""
    user_id: str
    first_name: str
    last_name: str
    vacation_days: float
    remaining_vacation_days: float
    sick_days: float
    training_days: float
    other_days: float
    overtime_year: float
    total_days: float
