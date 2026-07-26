from pydantic import BaseModel, ConfigDict, Field, field_serializer
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


class WorkingHoursChangeBase(BaseModel):
    effective_from: date
    weekly_hours: float = Field(..., ge=0, le=60)
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

    model_config = ConfigDict(from_attributes=True)


class WorkingHoursChangePreview(BaseModel):
    """Strikt lesende Vorschau vor dem Speichern einer Wochenstunden-Änderung.

    Zeigt, was eine (ggf. rückwirkende) Änderung anfassen WÜRDE — ohne selbst
    etwas zu schreiben. ``blocked_reason``/``closed_year_warning`` == None
    heißt „kein Problem"; ist ``blocked_reason`` gesetzt, würde der
    schreibende POST-Endpoint mit HTTP 400 ablehnen.
    """
    is_retroactive: bool
    period_start: date
    period_end: date
    current_daily_target: float
    new_daily_target: float
    affected_absences: int
    blocked_reason: Optional[str] = None
    closed_year_warning: Optional[str] = None
