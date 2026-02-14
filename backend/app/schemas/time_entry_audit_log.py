from pydantic import BaseModel, field_serializer
from typing import Optional
from datetime import date, time, datetime
from uuid import UUID


class AuditLogResponse(BaseModel):
    id: UUID
    time_entry_id: Optional[UUID] = None
    user_id: UUID
    changed_by: UUID
    action: str

    old_date: Optional[date] = None
    old_start_time: Optional[time] = None
    old_end_time: Optional[time] = None
    old_break_minutes: Optional[int] = None
    old_note: Optional[str] = None

    new_date: Optional[date] = None
    new_start_time: Optional[time] = None
    new_end_time: Optional[time] = None
    new_break_minutes: Optional[int] = None
    new_note: Optional[str] = None

    source: str
    change_request_id: Optional[UUID] = None

    # Joined fields for display
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    changed_by_first_name: Optional[str] = None
    changed_by_last_name: Optional[str] = None

    created_at: datetime

    @field_serializer('id', 'time_entry_id', 'user_id', 'changed_by', 'change_request_id')
    def serialize_uuid(self, value):
        return str(value) if value else None

    class Config:
        from_attributes = True
