from sqlalchemy import Column, Date, String, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class CompanyClosure(Base):
    """Company-wide closure (Betriebsferien) that creates vacation for all employees."""

    __tablename__ = "company_closures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    # #145: whether the generated absences deduct the vacation budget
    # (VACATION, default = legacy behaviour) or are paid leave like a
    # public holiday (PAID_LEAVE, no vacation deduction). The closure row
    # stores the choice so a later PUT re-sync keeps the absence type
    # consistent with what the admin selected.
    counts_as_vacation = Column(Boolean, nullable=False, server_default="true", default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<CompanyClosure(name={self.name}, {self.start_date}–{self.end_date})>"
