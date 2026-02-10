from pydantic import BaseModel, Field, field_serializer
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
    pass


class AbsenceResponse(AbsenceBase):
    id: UUID
    user_id: UUID
    end_date: Optional[date] = None
    created_at: datetime

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    class Config:
        from_attributes = True


class AbsenceCalendarEntry(BaseModel):
    """Entry for the absence calendar showing all employees."""
    date: date
    user_first_name: str
    user_last_name: str
    type: AbsenceType
    hours: float

    class Config:
        from_attributes = True


class TeamAbsenceEntry(BaseModel):
    """Entry for team absence overview with date range support."""
    date: date
    end_date: Optional[date] = None
    user_first_name: str
    user_last_name: str
    user_color: str
    type: AbsenceType
    hours: float
    note: Optional[str] = None

    class Config:
        from_attributes = True
