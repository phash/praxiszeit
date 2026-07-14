import re
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator
from typing import Optional
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID
from app.models.user import UserRole
from app.schemas.validators import validate_employment_and_window_order


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
    exempt_from_arbzg: bool = False  # §18 ArbZG: leitende Angestellte
    is_night_worker: bool = False  # §6 Abs. 2 ArbZG: Nachtarbeitnehmer (8h-Tageslimit)
    milog_working_time_account: bool = False  # #377 §2 Abs.2 MiLoG: Arbeitszeitkonto-Prüfungen
    agreed_monthly_hours: Optional[float] = Field(None, gt=0, le=400)  # #377 Baustein 2a: vereinbarte Monatszeit; None = aus weekly_hours
    use_fixed_monthly_target: bool = False  # #377 Baustein 2b: festes Monats-Soll = agreed_monthly_hours
    receives_company_closures: bool = True  # #189: nimmt an Betriebsferien teil (rollenunabhängig)
    first_work_day: Optional[date] = None  # Erster Arbeitstag
    last_work_day: Optional[date] = None   # Letzter Arbeitstag
    department: Optional[str] = Field(None, max_length=100)  # #162: Abteilung/Bereich
    child_sick_days_per_year: Optional[int] = Field(None, ge=0, le=70)  # #376 §45 SGB V; None = Tenant-Default
    # #201: Soll-Zeitfenster pro Wochentag
    scheduled_start_monday: Optional[time] = None
    scheduled_end_monday: Optional[time] = None
    scheduled_start_tuesday: Optional[time] = None
    scheduled_end_tuesday: Optional[time] = None
    scheduled_start_wednesday: Optional[time] = None
    scheduled_end_wednesday: Optional[time] = None
    scheduled_start_thursday: Optional[time] = None
    scheduled_end_thursday: Optional[time] = None
    scheduled_start_friday: Optional[time] = None
    scheduled_end_friday: Optional[time] = None

    @model_validator(mode='after')
    def check_work_day_order(self):
        return validate_employment_and_window_order(self)  # #219: shared

    @model_validator(mode='after')
    def check_fixed_monthly_target_requirements(self):
        # #377 Baustein 2b: festes Monats-Soll setzt vereinbarte Monatsarbeitszeit,
        # Stundenzählung UND das MiLoG-Arbeitszeitkonto voraus (koppelt an die
        # Task-9-Warnungen, die milog-gated sind).
        if self.use_fixed_monthly_target:
            if not self.agreed_monthly_hours or self.agreed_monthly_hours <= 0:
                raise ValueError("Fester Monats-Soll braucht eine vereinbarte Monatsarbeitszeit (> 0).")
            if not self.track_hours:
                raise ValueError("Fester Monats-Soll setzt Stundenzählung (track_hours) voraus.")
            if not self.milog_working_time_account:
                raise ValueError("Fester Monats-Soll setzt das MiLoG-Arbeitszeitkonto voraus.")
        return self


class UserCreate(UserBase):
    password: str = Field(..., min_length=10)
    role: UserRole = UserRole.EMPLOYEE

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[UserRole] = None
    email: Optional[str] = None
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    weekly_hours: Optional[float] = Field(None, ge=0, le=60)
    vacation_days: Optional[int] = Field(None, ge=0, le=50)
    work_days_per_week: Optional[int] = Field(None, ge=1, le=7)
    track_hours: Optional[bool] = None
    is_active: Optional[bool] = None
    is_hidden: Optional[bool] = None
    calendar_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    vacation_carryover_deadline: Optional[date] = None  # Individual deadline, None = default
    use_daily_schedule: Optional[bool] = None
    hours_monday: Optional[float] = Field(None, ge=0, le=24)
    hours_tuesday: Optional[float] = Field(None, ge=0, le=24)
    hours_wednesday: Optional[float] = Field(None, ge=0, le=24)
    hours_thursday: Optional[float] = Field(None, ge=0, le=24)
    hours_friday: Optional[float] = Field(None, ge=0, le=24)
    exempt_from_arbzg: Optional[bool] = None  # §18 ArbZG
    is_night_worker: Optional[bool] = None  # §6 Abs. 2 ArbZG
    milog_working_time_account: Optional[bool] = None  # #377 §2 Abs.2 MiLoG
    agreed_monthly_hours: Optional[float] = Field(None, gt=0, le=400)  # #377 Baustein 2a
    use_fixed_monthly_target: Optional[bool] = None  # #377 Baustein 2b
    receives_company_closures: Optional[bool] = None  # #189: Betriebsferien-Teilnahme
    first_work_day: Optional[date] = None   # Erster Arbeitstag
    last_work_day: Optional[date] = None    # Letzter Arbeitstag
    department: Optional[str] = Field(None, max_length=100)  # #162: Abteilung/Bereich
    child_sick_days_per_year: Optional[int] = Field(None, ge=0, le=70)  # #376
    # #201: Soll-Zeitfenster pro Wochentag
    scheduled_start_monday: Optional[time] = None
    scheduled_end_monday: Optional[time] = None
    scheduled_start_tuesday: Optional[time] = None
    scheduled_end_tuesday: Optional[time] = None
    scheduled_start_wednesday: Optional[time] = None
    scheduled_end_wednesday: Optional[time] = None
    scheduled_start_thursday: Optional[time] = None
    scheduled_end_thursday: Optional[time] = None
    scheduled_start_friday: Optional[time] = None
    scheduled_end_friday: Optional[time] = None

    @model_validator(mode='after')
    def check_work_day_order(self):
        return validate_employment_and_window_order(self)  # #219: shared

    @model_validator(mode='after')
    def check_fixed_monthly_target_requirements(self):
        # #377 Baustein 2b: partial update — only enforce when THIS payload sets
        # the flag True. A partial update that turns the flag on must carry all
        # three prerequisites explicitly in the same payload (None is treated
        # the same as False here — the validator only sees this payload, not the
        # persisted row, so it cannot assume an existing True elsewhere).
        # Updates that don't touch the flag (None/unset) are unaffected, so
        # existing partial-update flows for other fields keep working.
        if self.use_fixed_monthly_target:
            if not self.agreed_monthly_hours or self.agreed_monthly_hours <= 0:
                raise ValueError("Fester Monats-Soll braucht eine vereinbarte Monatsarbeitszeit (> 0).")
            if self.track_hours is not True:
                raise ValueError("Fester Monats-Soll setzt Stundenzählung (track_hours) voraus.")
            if self.milog_working_time_account is not True:
                raise ValueError("Fester Monats-Soll setzt das MiLoG-Arbeitszeitkonto voraus.")
        return self


class UserResponse(UserBase):
    id: UUID
    role: UserRole
    is_active: bool
    is_hidden: bool = False
    exempt_from_arbzg: bool = False  # §18 ArbZG
    is_night_worker: bool = False  # §6 Abs. 2 ArbZG
    totp_enabled: bool = False  # F-019: 2FA status
    profile_picture: Optional[str] = None
    deactivated_at: Optional[datetime] = None  # Grace-Period-Start
    onboarding_completed_at: Optional[datetime] = None  # NULL = Onboarding noch nicht gesehen
    created_at: datetime
    suggested_vacation_days: int
    vacation_carryover_deadline: Optional[date] = None

    @field_serializer('id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    """Lightweight user response for list endpoints – excludes profile_picture blob."""
    id: UUID
    role: UserRole
    username: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    weekly_hours: float
    vacation_days: int
    work_days_per_week: int
    track_hours: bool
    is_active: bool
    is_hidden: bool = False
    calendar_color: str = '#93C5FD'
    use_daily_schedule: bool = False
    hours_monday: Optional[float] = None
    hours_tuesday: Optional[float] = None
    hours_wednesday: Optional[float] = None
    hours_thursday: Optional[float] = None
    hours_friday: Optional[float] = None
    exempt_from_arbzg: bool = False
    is_night_worker: bool = False
    milog_working_time_account: bool = False  # #377 §2 Abs.2 MiLoG
    agreed_monthly_hours: Optional[float] = None  # #377 Baustein 2a (wie #376: hier PFLICHT, sonst Edit-Reset)
    use_fixed_monthly_target: bool = False  # #377 Baustein 2b (wie #376/#377: hier PFLICHT, sonst Edit-Reset)
    receives_company_closures: bool = True  # #189: Betriebsferien-Teilnahme
    first_work_day: Optional[date] = None
    last_work_day: Optional[date] = None
    department: Optional[str] = None  # #162: Abteilung/Bereich
    child_sick_days_per_year: Optional[int] = None  # #376 (latenter Bug: fehlte hier → Edit-Reset)
    # #201: Soll-Zeitfenster pro Wochentag
    scheduled_start_monday: Optional[time] = None
    scheduled_end_monday: Optional[time] = None
    scheduled_start_tuesday: Optional[time] = None
    scheduled_end_tuesday: Optional[time] = None
    scheduled_start_wednesday: Optional[time] = None
    scheduled_end_wednesday: Optional[time] = None
    scheduled_start_thursday: Optional[time] = None
    scheduled_end_thursday: Optional[time] = None
    scheduled_start_friday: Optional[time] = None
    scheduled_end_friday: Optional[time] = None
    totp_enabled: bool = False
    deactivated_at: Optional[datetime] = None
    created_at: datetime
    suggested_vacation_days: int
    vacation_carryover_deadline: Optional[date] = None

    @field_serializer('id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    totp_code: Optional[str] = Field(None, pattern=r'^\d{6}$')  # F-019: optional TOTP code


class LoginResponse(BaseModel):
    """F-010: refresh_token removed – delivered as HttpOnly cookie instead.
    profile_picture is excluded here (up to ~690 KB); fetch it lazily via GET /api/auth/me."""
    access_token: str
    token_type: str = "bearer"
    user: UserListResponse


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


# F-019: TOTP 2FA schemas

class TotpSetupResponse(BaseModel):
    otpauth_uri: str
    secret: str


class TotpVerifyRequest(BaseModel):
    code: str = Field(..., pattern=r'^\d{6}$')


class TotpDisableRequest(BaseModel):
    password: str = Field(..., min_length=1)
