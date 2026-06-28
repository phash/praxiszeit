from sqlalchemy import Column, Date, Time, Integer, String, Text, DateTime, Numeric, Enum, ForeignKey
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
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    request_type = Column(Enum(ChangeRequestType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    status = Column(Enum(ChangeRequestStatus, values_callable=lambda e: [x.value for x in e]), default=ChangeRequestStatus.PENDING, nullable=False, index=True)

    # Reference to existing time entry (nullable for CREATE requests)
    time_entry_id = Column(UUID(as_uuid=True), ForeignKey("time_entries.id", ondelete="SET NULL"), nullable=True, index=True)

    # Discriminator: 'time_entry' or 'absence'
    entry_kind = Column(String(20), nullable=False, server_default='time_entry')  # 'time_entry' | 'absence'

    # Reference to existing absence (for absence CRs).
    # Fix #1: ondelete="SET NULL" — without it, deleting an absence referenced by
    # a ChangeRequest raises a ForeignKeyViolation (500) on Postgres, breaking
    # absence deletion / refund / DSGVO purge. Mirrors time_entry_id above.
    absence_id = Column(
        UUID(as_uuid=True), ForeignKey("absences.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Absence proposed/original fields
    proposed_absence_type = Column(String(20), nullable=True)
    proposed_absence_hours = Column(Numeric(4, 2), nullable=True)
    original_absence_type = Column(String(20), nullable=True)
    original_absence_hours = Column(Numeric(4, 2), nullable=True)
    # #312: optional custom absence reason carried through the CR workflow.
    proposed_reason_id = Column(
        UUID(as_uuid=True), ForeignKey("absence_reasons.id", ondelete="SET NULL"), nullable=True, index=True,
    )

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

    # #144 §4 ArbZG: when this CR documents a "Pflicht-Pause war nicht möglich"
    # waiver, this holds the waiver reason. On approval it is copied to the
    # materialised time_entry's break_waiver_reason so the §4 deviation stays
    # auditable. NULL for all non-waiver CRs.
    break_waiver_reason = Column(Text, nullable=True)

    # Admin review
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<ChangeRequest(id={self.id}, type={self.request_type}, status={self.status})>"
