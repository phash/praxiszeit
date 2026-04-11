from sqlalchemy import Column, Date, Time, Text, DateTime, Numeric, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.database import Base


class AbsenceType(str, enum.Enum):
    """Absence type enumeration.

    Business rules (enforced in calculation_service.get_monthly_target /
    get_monthly_actual — any change here also needs a change there):

    - VACATION:  reduces monthly TARGET, adds 0 to ACTUAL. Decreases the
                 vacation budget. Net effect on overtime balance: 0.
    - SICK:      neutral to TARGET (§3 EntgFG — credited as if worked).
                 Adds the planned hours to ACTUAL. No effect on balance.
    - TRAINING:  same as SICK — treated as worked time (außer Haus).
    - OVERTIME:  Überstundenausgleich. TARGET stays as on a normal workday,
                 ACTUAL is 0, so the balance drops by one day's target —
                 which is exactly the intended "cash-out" of overtime.
    - OTHER:     UNPAID leave / Sonderurlaub-ohne-Bezug. Reduces TARGET
                 AND adds 0 to ACTUAL (no effect on balance, hours drop
                 out of both sides). Explicitly NOT paid leave. If you
                 need paid "Sonderurlaub", use VACATION and track the
                 reason in the note field.
    """
    VACATION = "vacation"
    SICK = "sick"
    TRAINING = "training"
    OVERTIME = "overtime"
    OTHER = "other"


class Absence(Base):
    """Absence model for tracking vacation, sick days, etc."""

    __tablename__ = "absences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # Start date (or single day if end_date is NULL)
    end_date = Column(Date, nullable=True, index=True)  # End date for date ranges (NULL for single day)
    type = Column(Enum(AbsenceType), nullable=False)
    hours = Column(Numeric(4, 2), nullable=False)  # Hours absent per day
    start_time = Column(Time, nullable=True)  # NULL = ganzer Tag
    end_time = Column(Time, nullable=True)    # NULL = ganzer Tag
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'user_id', 'date', 'type', name='uq_tenant_user_date_type'),
    )

    def __repr__(self):
        return f"<Absence(id={self.id}, user_id={self.user_id}, date={self.date}, type={self.type}, hours={self.hours})>"
