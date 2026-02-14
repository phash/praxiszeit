from sqlalchemy import Column, Date, Time, Integer, Text, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.database import Base


class ChangeRequestType(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class ChangeRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChangeRequest(Base):
    """Change request for time entries that employees cannot edit directly."""

    __tablename__ = "change_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    request_type = Column(Enum(ChangeRequestType), nullable=False)
    status = Column(Enum(ChangeRequestStatus), default=ChangeRequestStatus.PENDING, nullable=False, index=True)

    # Reference to existing time entry (nullable for CREATE requests)
    time_entry_id = Column(UUID(as_uuid=True), ForeignKey("time_entries.id", ondelete="SET NULL"), nullable=True, index=True)

    # Proposed values (for CREATE and UPDATE)
    proposed_date = Column(Date, nullable=True)
    proposed_start_time = Column(Time, nullable=True)
    proposed_end_time = Column(Time, nullable=True)
    proposed_break_minutes = Column(Integer, nullable=True)
    proposed_note = Column(Text, nullable=True)

    # Original values snapshot (for UPDATE and DELETE)
    original_date = Column(Date, nullable=True)
    original_start_time = Column(Time, nullable=True)
    original_end_time = Column(Time, nullable=True)
    original_break_minutes = Column(Integer, nullable=True)
    original_note = Column(Text, nullable=True)

    # Employee reason
    reason = Column(Text, nullable=False)

    # Admin review
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<ChangeRequest(id={self.id}, type={self.request_type}, status={self.status})>"
