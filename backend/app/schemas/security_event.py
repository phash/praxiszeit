"""#489: Lese-Sicht auf ``security_events`` fuer die Verwaltung."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class SecurityEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    event: str
    subject_user_id: Optional[UUID] = None
    subject_name: Optional[str] = None
    actor: str
    actor_name: str
    detail: Optional[str] = None

    @field_serializer('id', 'subject_user_id')
    def _uuid_to_str(self, value):
        return str(value) if value is not None else None
