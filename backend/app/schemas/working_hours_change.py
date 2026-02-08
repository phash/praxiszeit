from pydantic import BaseModel, Field, field_serializer
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


class WorkingHoursChangeBase(BaseModel):
    effective_from: date
    weekly_hours: Decimal = Field(..., ge=0, le=60)
    note: Optional[str] = None


class WorkingHoursChangeCreate(WorkingHoursChangeBase):
    pass


class WorkingHoursChangeResponse(WorkingHoursChangeBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    class Config:
        from_attributes = True
