from pydantic import BaseModel, ConfigDict, Field, field_serializer
from uuid import UUID
from datetime import datetime
from typing import Optional


class YearCarryoverCreate(BaseModel):
    """Create or update year carryover for a user."""
    overtime_hours: float = Field(default=0, ge=-9999, le=9999)
    vacation_days: float = Field(default=0, ge=-50, le=50)


class YearCarryoverResponse(BaseModel):
    """Year carryover response."""
    id: UUID
    user_id: UUID
    year: int
    overtime_hours: float
    vacation_days: float
    created_at: datetime
    updated_at: datetime

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    model_config = ConfigDict(from_attributes=True)
