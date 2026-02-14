from pydantic import BaseModel, Field, field_validator, field_serializer
from typing import Optional
from datetime import date, time, datetime
from decimal import Decimal
from uuid import UUID


class TimeEntryBase(BaseModel):
    date: date
    start_time: time
    end_time: time
    break_minutes: int = Field(default=0, ge=0)
    note: Optional[str] = None

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


class TimeEntryResponse(TimeEntryBase):
    id: UUID
    user_id: UUID
    net_hours: float
    is_editable: bool = True
    created_at: datetime

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    class Config:
        from_attributes = True
