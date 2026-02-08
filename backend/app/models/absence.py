from sqlalchemy import Column, Date, Text, DateTime, Numeric, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.database import Base


class AbsenceType(str, enum.Enum):
    """Absence type enumeration."""
    VACATION = "vacation"
    SICK = "sick"
    TRAINING = "training"
    OTHER = "other"


class Absence(Base):
    """Absence model for tracking vacation, sick days, etc."""

    __tablename__ = "absences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # Start date (or single day if end_date is NULL)
    end_date = Column(Date, nullable=True, index=True)  # End date for date ranges (NULL for single day)
    type = Column(Enum(AbsenceType), nullable=False)
    hours = Column(Numeric(4, 2), nullable=False)  # Hours absent per day
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'date', 'type', name='uq_user_date_type'),
    )

    def __repr__(self):
        return f"<Absence(id={self.id}, user_id={self.user_id}, date={self.date}, type={self.type}, hours={self.hours})>"
