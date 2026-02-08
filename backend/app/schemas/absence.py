from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from app.models.absence import AbsenceType


class AbsenceBase(BaseModel):
    date: date  # Start date
    end_date: Optional[date] = None  # End date for ranges (NULL for single day)
    type: AbsenceType
    hours: Decimal = Field(..., ge=0, le=24)  # Hours per day
    note: Optional[str] = None


class AbsenceCreate(AbsenceBase):
    pass


class AbsenceResponse(AbsenceBase):
    id: str
    user_id: str
    end_date: Optional[date] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AbsenceCalendarEntry(BaseModel):
    """Entry for the absence calendar showing all employees."""
    date: date
    user_first_name: str
    user_last_name: str
    type: AbsenceType
    hours: Decimal

    class Config:
        from_attributes = True
