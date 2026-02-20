import re
from pydantic import BaseModel, Field, field_serializer, field_validator
from typing import Optional
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from app.models.user import UserRole


def _validate_password_complexity(password: str) -> str:
    """Validate password meets complexity requirements."""
    if len(password) < 10:
        raise ValueError("Passwort muss mindestens 10 Zeichen lang sein")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Passwort muss mindestens einen Grossbuchstaben enthalten")
    if not re.search(r"[a-z]", password):
        raise ValueError("Passwort muss mindestens einen Kleinbuchstaben enthalten")
    if not re.search(r"[0-9]", password):
        raise ValueError("Passwort muss mindestens eine Ziffer enthalten")
    return password


class DailySchedule(BaseModel):
    hours_monday: Optional[float] = Field(None, ge=0, le=24)
    hours_tuesday: Optional[float] = Field(None, ge=0, le=24)
    hours_wednesday: Optional[float] = Field(None, ge=0, le=24)
    hours_thursday: Optional[float] = Field(None, ge=0, le=24)
    hours_friday: Optional[float] = Field(None, ge=0, le=24)


class UserBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = None
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    weekly_hours: float = Field(..., ge=0, le=60)
    vacation_days: int = Field(..., ge=0, le=50)
    work_days_per_week: int = Field(default=5, ge=1, le=7)
    track_hours: bool = True
    calendar_color: str = Field(default='#93C5FD', pattern=r'^#[0-9A-Fa-f]{6}$')
    use_daily_schedule: bool = False
    hours_monday: Optional[float] = Field(None, ge=0, le=24)
    hours_tuesday: Optional[float] = Field(None, ge=0, le=24)
    hours_wednesday: Optional[float] = Field(None, ge=0, le=24)
    hours_thursday: Optional[float] = Field(None, ge=0, le=24)
    hours_friday: Optional[float] = Field(None, ge=0, le=24)


class UserCreate(UserBase):
    password: str = Field(..., min_length=10)
    role: UserRole = UserRole.EMPLOYEE

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = None
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    weekly_hours: Optional[float] = Field(None, ge=0, le=60)
    vacation_days: Optional[int] = Field(None, ge=0, le=50)
    work_days_per_week: Optional[int] = Field(None, ge=1, le=7)
    track_hours: Optional[bool] = None
    is_active: Optional[bool] = None
    is_hidden: Optional[bool] = None
    vacation_carryover_deadline: Optional[date] = None  # Individual deadline, None = default
    use_daily_schedule: Optional[bool] = None
    hours_monday: Optional[float] = Field(None, ge=0, le=24)
    hours_tuesday: Optional[float] = Field(None, ge=0, le=24)
    hours_wednesday: Optional[float] = Field(None, ge=0, le=24)
    hours_thursday: Optional[float] = Field(None, ge=0, le=24)
    hours_friday: Optional[float] = Field(None, ge=0, le=24)


class UserResponse(UserBase):
    id: UUID
    role: UserRole
    is_active: bool
    is_hidden: bool = False
    created_at: datetime
    suggested_vacation_days: int
    vacation_carryover_deadline: Optional[date] = None

    @field_serializer('id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminSetPassword(BaseModel):
    password: str = Field(..., min_length=10)

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class UserCreateResponse(BaseModel):
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=10)

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class UpdateCalendarColorRequest(BaseModel):
    calendar_color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$')
