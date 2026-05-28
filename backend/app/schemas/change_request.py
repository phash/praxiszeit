from pydantic import BaseModel, ConfigDict, Field, field_serializer
from typing import List, Optional
from datetime import date, time, datetime
from uuid import UUID


class ChangeRequestCreate(BaseModel):
    request_type: str  # "create", "update", "delete"
    time_entry_id: Optional[str] = None  # required for update/delete
    entry_kind: str = "time_entry"  # 'time_entry' | 'absence'
    absence_id: Optional[str] = None
    proposed_date: Optional[date] = None
    proposed_start_time: Optional[time] = None
    proposed_end_time: Optional[time] = None
    proposed_break_minutes: Optional[int] = Field(None, ge=0)
    proposed_note: Optional[str] = None
    proposed_absence_type: Optional[str] = None
    proposed_absence_hours: Optional[float] = None
    reason: str = Field(..., min_length=1)
    # SEC-D: cap length to prevent storage DoS via unbounded free text.
    break_waiver_reason: Optional[str] = Field(None, max_length=2000)  # #144 §4 ArbZG


class ChangeRequestReview(BaseModel):
    action: str  # "approve" or "reject"
    rejection_reason: Optional[str] = None


class ChangeRequestBulkReview(BaseModel):
    request_ids: List[UUID] = Field(..., min_length=1, max_length=200)
    action: str  # "approve" or "reject"
    rejection_reason: Optional[str] = None


class ChangeRequestBulkReviewItemResult(BaseModel):
    request_id: UUID
    status: str  # "approved" | "rejected" | "failed"
    error: Optional[str] = None

    @field_serializer('request_id')
    def serialize_request_id(self, value):
        return str(value)


class ChangeRequestBulkReviewResult(BaseModel):
    succeeded: int
    failed: int
    items: List[ChangeRequestBulkReviewItemResult]


class ChangeRequestResponse(BaseModel):
    id: UUID
    user_id: UUID
    request_type: str
    status: str
    time_entry_id: Optional[UUID] = None
    entry_kind: str = "time_entry"
    absence_id: Optional[UUID] = None

    proposed_date: Optional[date] = None
    proposed_start_time: Optional[time] = None
    proposed_end_time: Optional[time] = None
    proposed_break_minutes: Optional[int] = None
    proposed_note: Optional[str] = None

    proposed_absence_type: Optional[str] = None
    proposed_absence_hours: Optional[float] = None

    original_date: Optional[date] = None
    original_start_time: Optional[time] = None
    original_end_time: Optional[time] = None
    original_break_minutes: Optional[int] = None
    original_note: Optional[str] = None
    original_absence_type: Optional[str] = None
    original_absence_hours: Optional[float] = None

    reason: str
    break_waiver_reason: Optional[str] = None  # #144 §4 ArbZG
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
    warnings: List[str] = []

    @field_serializer('id', 'user_id', 'time_entry_id', 'absence_id', 'reviewed_by')
    def serialize_uuid(self, value):
        return str(value) if value else None

    model_config = ConfigDict(from_attributes=True)
