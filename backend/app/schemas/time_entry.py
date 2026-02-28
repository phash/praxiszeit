from pydantic import BaseModel, Field, field_validator, field_serializer
from typing import Optional, List
from datetime import date, time, datetime
from decimal import Decimal
from uuid import UUID


class TimeEntryBase(BaseModel):
    date: date
    start_time: time
    end_time: time
    break_minutes: int = Field(default=0, ge=0)
    note: Optional[str] = None
    sunday_exception_reason: Optional[str] = None  # §10 ArbZG

    @field_validator('end_time')
    @classmethod
    def validate_end_after_start(cls, v, info):
        if 'start_time' in info.data and v <= info.data['start_time']:
            raise ValueError('Endzeit muss nach Startzeit liegen')
        return v

    @field_validator('date')
    @classmethod
    def validate_not_future(cls, v):
        if v > date.today():
            raise ValueError('Datum darf nicht in der Zukunft liegen')
        return v


class TimeEntryCreate(TimeEntryBase):
    pass


class TimeEntryUpdate(BaseModel):
    date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = Field(None, ge=0)
    note: Optional[str] = None
    sunday_exception_reason: Optional[str] = None  # §10 ArbZG


class TimeEntryResponse(BaseModel):
    id: UUID
    user_id: UUID
    date: date
    start_time: time
    end_time: Optional[time] = None
    break_minutes: int = Field(default=0, ge=0)
    note: Optional[str] = None
    net_hours: float
    is_editable: bool = True
    warnings: List[str] = []
    is_sunday_or_holiday: bool = False
    is_night_work: bool = False
    sunday_exception_reason: Optional[str] = None  # §10 ArbZG
    created_at: datetime

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    class Config:
        from_attributes = True


# --- Clock-in/out schemas ---

class ClockInRequest(BaseModel):
    note: Optional[str] = None


class ClockOutRequest(BaseModel):
    break_minutes: int = Field(default=0, ge=0)
    note: Optional[str] = None


class ClockStatusResponse(BaseModel):
    is_clocked_in: bool
    current_entry: Optional[TimeEntryResponse] = None
    elapsed_minutes: Optional[int] = None
