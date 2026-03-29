from pydantic import BaseModel, ConfigDict, Field, field_serializer
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from app.models.absence import AbsenceType


class AbsenceBase(BaseModel):
    date: date  # Start date
    end_date: Optional[date] = None  # End date for ranges (NULL for single day)
    type: AbsenceType
    hours: float = Field(..., ge=0, le=24)  # Hours per day
    note: Optional[str] = None


class AbsenceCreate(AbsenceBase):
    user_id: Optional[str] = None  # Admin only: create absence for another user
    refund_vacation: bool = False  # If sick: refund overlapping vacation days


class AbsenceResponse(AbsenceBase):
    id: UUID
    user_id: UUID
    end_date: Optional[date] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)


class AbsenceCalendarEntry(BaseModel):
    """Entry for the absence calendar showing all employees."""
    model_config = ConfigDict(from_attributes=True)

    date: date
    user_first_name: str
    user_last_name: str
    type: AbsenceType
    hours: float


class TeamAbsenceEntry(BaseModel):
    """Entry for team absence overview with date range support."""
    model_config = ConfigDict(from_attributes=True)

    date: date
    end_date: Optional[date] = None
    user_first_name: str
    user_last_name: str
    user_color: str
    type: AbsenceType
    hours: float


class NextVacationResponse(BaseModel):
    """Response for the next upcoming vacation countdown."""
    date: date
    end_date: Optional[date] = None
    days_until: int
