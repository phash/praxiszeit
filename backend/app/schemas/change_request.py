from pydantic import BaseModel, Field, field_serializer
from typing import Optional
from datetime import date, time, datetime
from uuid import UUID


class ChangeRequestCreate(BaseModel):
    request_type: str  # "create", "update", "delete"
    time_entry_id: Optional[str] = None  # required for update/delete
    proposed_date: Optional[date] = None
    proposed_start_time: Optional[time] = None
    proposed_end_time: Optional[time] = None
    proposed_break_minutes: Optional[int] = Field(None, ge=0)
    proposed_note: Optional[str] = None
    reason: str = Field(..., min_length=1)


class ChangeRequestReview(BaseModel):
    action: str  # "approve" or "reject"
    rejection_reason: Optional[str] = None


class ChangeRequestResponse(BaseModel):
    id: UUID
    user_id: UUID
    request_type: str
    status: str
    time_entry_id: Optional[UUID] = None

    proposed_date: Optional[date] = None
    proposed_start_time: Optional[time] = None
    proposed_end_time: Optional[time] = None
    proposed_break_minutes: Optional[int] = None
    proposed_note: Optional[str] = None

    original_date: Optional[date] = None
    original_start_time: Optional[time] = None
    original_end_time: Optional[time] = None
    original_break_minutes: Optional[int] = None
    original_note: Optional[str] = None

    reason: str
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    # Joined fields for display
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    reviewer_first_name: Optional[str] = None
    reviewer_last_name: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    @field_serializer('id', 'user_id', 'time_entry_id', 'reviewed_by')
    def serialize_uuid(self, value):
        return str(value) if value else None

    class Config:
        from_attributes = True
