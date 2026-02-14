from sqlalchemy import Column, String, Date, Time, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class TimeEntryAuditLog(Base):
    """Audit log for all changes to time entries."""

    __tablename__ = "time_entry_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time_entry_id = Column(UUID(as_uuid=True), ForeignKey("time_entries.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)  # affected employee
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)  # admin who made change

    action = Column(String(20), nullable=False)  # "create", "update", "delete"

    # Old values (null for create)
    old_date = Column(Date, nullable=True)
    old_start_time = Column(Time, nullable=True)
    old_end_time = Column(Time, nullable=True)
    old_break_minutes = Column(Integer, nullable=True)
    old_note = Column(Text, nullable=True)

    # New values (null for delete)
    new_date = Column(Date, nullable=True)
    new_start_time = Column(Time, nullable=True)
    new_end_time = Column(Time, nullable=True)
    new_break_minutes = Column(Integer, nullable=True)
    new_note = Column(Text, nullable=True)

    source = Column(String(20), nullable=False, default="manual")  # "manual" or "change_request"
    change_request_id = Column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<TimeEntryAuditLog(id={self.id}, action={self.action}, user_id={self.user_id})>"
