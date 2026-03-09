from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional, Literal
import uuid


class VacationRequestCreate(BaseModel):
    date: date
    end_date: Optional[date] = None
    hours: float
    note: Optional[str] = None

    @field_validator('end_date')
    @classmethod
    def end_date_after_start(cls, v, info):
        if v is not None and 'date' in info.data and v < info.data['date']:
            raise ValueError('end_date muss nach date liegen')
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

    model_config = {"from_attributes": True}
