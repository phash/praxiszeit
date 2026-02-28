from sqlalchemy import Column, Date, Time, Integer, Text, DateTime, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
from decimal import Decimal
import uuid
from app.database import Base


class TimeEntry(Base):
    """Time entry model for tracking work hours."""

    __tablename__ = "time_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=True)
    break_minutes = Column(Integer, default=0, nullable=False)
    note = Column(Text, nullable=True)
    sunday_exception_reason = Column(Text, nullable=True)  # §10 ArbZG: reason for Sunday/holiday work
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'date', 'start_time', name='uq_user_date_start'),
    )

    @hybrid_property
    def net_hours(self) -> Decimal:
        """
        Calculate net hours worked (end - start - break).
        Returns hours as Decimal with 2 decimal places.
        """
        if not self.start_time or not self.end_time:
            return Decimal('0.00')

        # Convert times to total seconds
        start_seconds = self.start_time.hour * 3600 + self.start_time.minute * 60 + self.start_time.second
        end_seconds = self.end_time.hour * 3600 + self.end_time.minute * 60 + self.end_time.second

        # Calculate duration in hours
        duration_hours = (end_seconds - start_seconds) / 3600.0

        # Subtract break time
        break_hours = self.break_minutes / 60.0

        net = duration_hours - break_hours

        return Decimal(str(round(net, 2)))

    def __repr__(self):
        return f"<TimeEntry(id={self.id}, user_id={self.user_id}, date={self.date}, net_hours={self.net_hours})>"
