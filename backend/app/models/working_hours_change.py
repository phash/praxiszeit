from sqlalchemy import Column, String, Numeric, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class WorkingHoursChange(Base):
    """
    Historical record of working hours changes for a user.
    Allows tracking when a user's weekly hours changed (e.g., part-time adjustments).
    """

    __tablename__ = "working_hours_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_from = Column(Date, nullable=False, index=True)  # Date from which these hours are valid
    weekly_hours = Column(Numeric(4, 1), nullable=False)  # e.g., 20.0, 30.0, 38.5
    note = Column(String(500), nullable=True)  # Optional note about the change
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<WorkingHoursChange(user_id={self.user_id}, effective_from={self.effective_from}, weekly_hours={self.weekly_hours})>"
