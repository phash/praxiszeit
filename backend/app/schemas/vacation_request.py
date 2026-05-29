from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date, datetime
from datetime import date as _date_type
from typing import Optional, Literal
import uuid


class VacationRequestCreate(BaseModel):
    date: date
    end_date: Optional[date] = None
    hours: float
    note: Optional[str] = None
    absence_type: Optional[str] = "vacation"
    half_day: bool = False  # #167: halber Urlaubstag

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

    @field_validator('half_day')
    @classmethod
    def half_day_single_day(cls, v, info):
        # Halbe Tage sind ein Einzeltag-Konzept — ein Zeitraum mit half_day=True
        # würde jeden Tag des Bereichs halbieren (überraschend, inkonsistent zur UI).
        if v:
            start = info.data.get('date')
            end = info.data.get('end_date')
            if end is not None and start is not None and end != start:
                raise ValueError('Halbe Tage sind nur für Einzeltage möglich')
        return v


class VacationRequestUpdate(BaseModel):
    """Partial update for a PENDING vacation request.

    All fields optional — caller may patch any subset. The router
    re-validates the full effective state (start <= end, budget,
    work-day window, overlap with other pending) after merging.

    `extra="forbid"` rejects unknown fields so a future refactor that
    blindly assigns `data.model_dump(exclude_unset=True)` cannot become
    a mass-assignment vector (e.g. status, reviewed_by, user_id).
    """

    model_config = ConfigDict(extra="forbid")

    date: Optional[_date_type] = None
    end_date: Optional[_date_type] = None
    hours: Optional[float] = Field(None, ge=0, le=24)
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
    half_day: bool = False  # #167
    note: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Last-edit tracking (Issue: DSGVO transparency) — drives the
    # "Bearbeitet von Admin XY am ..." badge on the MA's view.
    last_modified_by: Optional[uuid.UUID] = None
    last_modified_at: Optional[datetime] = None
    last_modifier_first_name: Optional[str] = None
    last_modifier_last_name: Optional[str] = None

    # Enriched fields (populated by router)
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    reviewer_first_name: Optional[str] = None
    reviewer_last_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
