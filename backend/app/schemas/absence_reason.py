"""#312 Schemas for tenant-defined custom absence reasons."""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.absence import AbsenceReasonBehavior


class AbsenceReasonCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    color: Optional[str] = None  # #RRGGBB — validated in the router (→ 400)
    base_behavior: AbsenceReasonBehavior
    sort_order: int = 0


class AbsenceReasonUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    color: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    # base_behavior is intentionally NOT updatable (v1 lock): changing it would
    # make existing absences inconsistent with their stored ``type``.


class AbsenceReasonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: Optional[str] = None
    base_behavior: str
    is_active: bool
    sort_order: int
