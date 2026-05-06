from pydantic import BaseModel, ConfigDict, field_validator
import datetime as _dt
from datetime import date, datetime
from typing import Optional, Literal
import uuid


class VacationRequestCreate(BaseModel):
    date: date
    end_date: Optional[date] = None
    hours: float
    note: Optional[str] = None
    absence_type: Optional[str] = "vacation"

    @field_validator('absence_type')
    @classmethod
    def validate_absence_type(cls, v):
        allowed = {"vacation", "training", "overtime", "other"}
        if v not in allowed:
            raise ValueError(f'absence_type muss einer von {allowed} sein')
        return v

    @field_validator('end_date')
    @classmethod
    def end_date_after_start(cls, v, info):
        if v is not None and 'date' in info.data and v < info.data['date']:
            raise ValueError('end_date muss nach date liegen')
        return v


class VacationRequestUpdate(BaseModel):
    """Partial update for a PENDING vacation request.

    All fields optional — caller may patch any subset. The router
    re-validates the full effective state (start <= end, budget,
    work-day window, overlap with other pending) after merging.
    """

    date: Optional[_dt.date] = None
    end_date: Optional[_dt.date] = None
    hours: Optional[float] = None
    note: Optional[str] = None
    absence_type: Optional[str] = None

    @field_validator('absence_type')
    @classmethod
    def validate_absence_type(cls, v):
        if v is None:
            return v
        allowed = {"vacation", "training", "overtime", "other"}
        if v not in allowed:
            raise ValueError(f'absence_type muss einer von {allowed} sein')
        return v


class VacationRequestReview(BaseModel):
    action: Literal["approve", "reject"]
    rejection_reason: Optional[str] = None


class VacationRequestResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    date: date
    end_date: Optional[date] = None
    hours: float
    days: Optional[float] = None  # Number of workdays (excluding weekends/holidays)
    absence_type: str = "vacation"
    note: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Enriched fields (populated by router)
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    reviewer_first_name: Optional[str] = None
    reviewer_last_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
