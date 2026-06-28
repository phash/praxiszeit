from sqlalchemy import Column, Numeric, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class YearCarryover(Base):
    """Stores overtime hours and vacation days carried over from the previous year."""

    __tablename__ = "year_carryovers"
    __table_args__ = (
        UniqueConstraint('tenant_id', 'user_id', 'year', name='uq_tenant_year_carryover_user_year'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)  # The year these carryovers apply TO
    overtime_hours = Column(Numeric(8, 2), nullable=False, default=0)  # Overtime hours from previous year
    vacation_days = Column(Numeric(4, 1), nullable=False, default=0)  # Vacation days from previous year
    # Fix #7: provenance — 'year_closing' (created/updated by create_year_closing,
    # removable via delete_year_closing) vs 'manual' (admin-entered via
    # upsert_carryover, must survive delete_year_closing).
    source = Column(String(20), nullable=False, default="year_closing", server_default="year_closing")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<YearCarryover(user_id={self.user_id}, year={self.year}, overtime={self.overtime_hours}h, vacation={self.vacation_days}d)>"
