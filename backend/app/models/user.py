from sqlalchemy import Column, String, Boolean, Numeric, Integer, BigInteger, Enum, DateTime, Date, Text, Time, ForeignKey
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
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    username = Column(String(100), nullable=False, index=True)
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
    # #201: optionales Soll-Arbeitszeit-Fenster je Wochentag (Mo–Fr). NULL =
    # kein Fenster an dem Tag → keine Kappung. Kappt nur das Ist, nicht das Soll.
    scheduled_start_monday = Column(Time, nullable=True)
    scheduled_end_monday = Column(Time, nullable=True)
    scheduled_start_tuesday = Column(Time, nullable=True)
    scheduled_end_tuesday = Column(Time, nullable=True)
    scheduled_start_wednesday = Column(Time, nullable=True)
    scheduled_end_wednesday = Column(Time, nullable=True)
    scheduled_start_thursday = Column(Time, nullable=True)
    scheduled_end_thursday = Column(Time, nullable=True)
    scheduled_start_friday = Column(Time, nullable=True)
    scheduled_end_friday = Column(Time, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False, server_default='false')  # Hidden from reports/overviews
    token_version = Column(Integer, default=0, nullable=False, server_default='0')  # Increment to invalidate all tokens
    exempt_from_arbzg = Column(Boolean, default=False, nullable=False, server_default='false')  # §18 ArbZG: leitende Angestellte
    is_night_worker = Column(Boolean, default=False, nullable=False, server_default='false')  # §6 Abs. 2 ArbZG: reduziertes Tageslimit 8h
    milog_working_time_account = Column(Boolean, default=False, nullable=False, server_default='false')  # #377 §2 Abs.2 MiLoG: Arbeitszeitkonto-Prüfungen (opt-in)
    agreed_monthly_hours = Column(Numeric(5, 1), nullable=True)  # #377 Baustein 2a: vereinbarte Monatsarbeitszeit; NULL = aus weekly_hours abgeleitet
    use_fixed_monthly_target = Column(Boolean, default=False, nullable=False, server_default='false')  # #377 Baustein 2b: festes Monats-Soll = agreed_monthly_hours
    receives_company_closures = Column(Boolean, default=True, nullable=False, server_default='true')  # #189: nimmt an Betriebsferien teil (unabhängig von der Rolle)
    department = Column(String(100), nullable=True)  # #162: Abteilung/Bereich (Freitext, optional)
    totp_secret = Column(String(255), nullable=True)  # F-019: TOTP secret, Fernet-encrypted at-rest (DSGVO Art.32); None if 2FA not set up
    totp_enabled = Column(Boolean, default=False, nullable=False, server_default='false')  # F-019: 2FA active
    last_totp_counter = Column(BigInteger, nullable=True)  # Highest counter value already accepted (replay guard)
    first_work_day = Column(Date, nullable=True)  # Erster Arbeitstag
    last_work_day = Column(Date, nullable=True)   # Letzter Arbeitstag
    # #376: persönlicher Kind-krank-Jahresanspruch (§45 SGB V). NULL = Tenant-Default
    # (Setting child_sick_days_default, sonst 15). Speichert KEINE Kinderdaten.
    child_sick_days_per_year = Column(Integer, nullable=True)
    profile_picture = Column(Text, nullable=True)  # Base64 data URI
    deactivated_at = Column(DateTime(timezone=True), nullable=True)  # Grace-Period-Start bei Deaktivierung
    onboarding_completed_at = Column(DateTime(timezone=True), nullable=True)  # NULL = Onboarding (Erst-Login-Tour) noch nicht gesehen
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def suggested_vacation_days(self) -> int:
        """Calculate vacation days per specification: 30 × (work_days / 5)."""
        return max(0, round(30 * (self.work_days_per_week or 5) / 5))

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
