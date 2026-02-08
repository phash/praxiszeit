from sqlalchemy import Column, String, Boolean, Numeric, Integer, Enum, DateTime
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
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.EMPLOYEE, nullable=False)
    weekly_hours = Column(Numeric(4, 1), nullable=False)  # e.g., 20.0, 30.0, 38.5
    vacation_days = Column(Integer, nullable=False, default=30)
    track_hours = Column(Boolean, default=True, nullable=False)  # Track Soll/Ist hours for this user
    calendar_color = Column(String(7), nullable=False, default='#93C5FD')  # Pastel blue default
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
