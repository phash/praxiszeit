from pydantic import BaseModel, EmailStr, Field, field_serializer
from typing import Optional
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    weekly_hours: float = Field(..., ge=0, le=60)
    vacation_days: int = Field(..., ge=0, le=50)
    work_days_per_week: int = Field(default=5, ge=1, le=7)
    track_hours: bool = True
    calendar_color: str = Field(default='#93C5FD', pattern=r'^#[0-9A-Fa-f]{6}$')


class UserCreate(UserBase):
    role: UserRole = UserRole.EMPLOYEE


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    weekly_hours: Optional[float] = Field(None, ge=0, le=60)
    vacation_days: Optional[int] = Field(None, ge=0, le=50)
    work_days_per_week: Optional[int] = Field(None, ge=1, le=7)
    track_hours: Optional[bool] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: UUID
    role: UserRole
    is_active: bool
    created_at: datetime
    suggested_vacation_days: int

    @field_serializer('id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: EmailStr
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


class PasswordResetResponse(BaseModel):
    message: str
    temporary_password: str


class UserCreateResponse(BaseModel):
    user: UserResponse
    temporary_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class UpdateCalendarColorRequest(BaseModel):
    calendar_color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$')
