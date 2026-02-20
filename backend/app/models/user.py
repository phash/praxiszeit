from sqlalchemy import Column, String, Boolean, Numeric, Integer, Enum, DateTime, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.database import Base


class UserRole(str, enum.Enum):
    """User role enumeration."""
    ADMIN = "admin"
    EMPLOYEE = "employee"


class User(Base):
    """User model for authentication and employee management."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.EMPLOYEE, nullable=False)
    weekly_hours = Column(Numeric(4, 1), nullable=False)  # e.g., 20.0, 30.0, 38.5
    vacation_days = Column(Integer, nullable=False, default=30)
    work_days_per_week = Column(Integer, nullable=False, default=5)
    track_hours = Column(Boolean, default=True, nullable=False)  # Track Soll/Ist hours for this user
    calendar_color = Column(String(7), nullable=False, default='#93C5FD')  # Pastel blue default
    vacation_carryover_deadline = Column(Date, nullable=True)  # NULL = default (March 31 next year)
    use_daily_schedule = Column(Boolean, default=False, nullable=False)
    hours_monday = Column(Numeric(4, 2), nullable=True)
    hours_tuesday = Column(Numeric(4, 2), nullable=True)
    hours_wednesday = Column(Numeric(4, 2), nullable=True)
    hours_thursday = Column(Numeric(4, 2), nullable=True)
    hours_friday = Column(Numeric(4, 2), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False, server_default='false')  # Hidden from reports/overviews
    token_version = Column(Integer, default=0, nullable=False, server_default='0')  # Increment to invalidate all tokens
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def suggested_vacation_days(self) -> int:
        """Calculate vacation days per specification: 30 × (work_days / 5)."""
        return round(30 * self.work_days_per_week / 5)

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
