"""#402: Voraussichtlicher Überstundensaldo zum Jahresende.

Kunde (philvdb): unter dem Überstundenkonto soll eine Zeile den projizierten
Saldo am 31.12. zeigen = aktueller Saldo − bereits feststehender künftiger
Freizeitausgleich (OVERTIME-Abwesenheiten in der Zukunft, typ. aus Betriebsferien
via #314). Bewusst Soll-basiert, damit die Projektion im Dezember bitgleich zum
dann tatsächlichen Saldo wird.
"""
import uuid
from datetime import date

from app.models import User, UserRole, Absence, AbsenceType
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _user(db, track_hours=True):
    u = User(
        id=uuid.uuid4(), username=f"o{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.l",
        password_hash="x", first_name="O", last_name="T", role=UserRole.EMPLOYEE,
        weekly_hours=40, work_days_per_week=5, vacation_days=30,
        track_hours=track_hours, use_daily_schedule=False, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _overtime(db, u, d):
    a = Absence(id=uuid.uuid4(), user_id=u.id, tenant_id=DEFAULT_TENANT_ID,
                date=d, type=AbsenceType.OVERTIME, hours=8)
    db.add(a); db.commit()
    return a


TODAY = date(2026, 7, 15)
CUTOFF = date(2026, 7, 14)


def test_future_overtime_day_counts_full_daily_soll(db):
    u = _user(db)
    _overtime(db, u, date(2026, 12, 1))  # Dienstag, Werktag, 8h Soll
    impact = calculation_service.future_freizeitausgleich_impact(db, u, cutoff_date=CUTOFF, today=TODAY)
    assert float(impact) == 8.0


def test_two_future_overtime_days_sum(db):
    u = _user(db)
    _overtime(db, u, date(2026, 12, 1))
    _overtime(db, u, date(2026, 12, 2))
    impact = calculation_service.future_freizeitausgleich_impact(db, u, cutoff_date=CUTOFF, today=TODAY)
    assert float(impact) == 16.0


def test_past_overtime_not_counted(db):
    """OVERTIME am/vor dem Stichtag ist schon im aktuellen Saldo → nicht doppelt."""
    u = _user(db)
    _overtime(db, u, date(2026, 7, 10))  # vor Cutoff
    impact = calculation_service.future_freizeitausgleich_impact(db, u, cutoff_date=CUTOFF, today=TODAY)
    assert float(impact) == 0.0


def test_next_year_overtime_excluded(db):
    """Nur bis 31.12. des laufenden Jahres."""
    u = _user(db)
    _overtime(db, u, date(2027, 1, 4))
    impact = calculation_service.future_freizeitausgleich_impact(db, u, cutoff_date=CUTOFF, today=TODAY)
    assert float(impact) == 0.0


def test_no_future_overtime_zero(db):
    u = _user(db)
    impact = calculation_service.future_freizeitausgleich_impact(db, u, cutoff_date=CUTOFF, today=TODAY)
    assert float(impact) == 0.0


def test_untracked_user_zero(db):
    u = _user(db, track_hours=False)
    _overtime(db, u, date(2026, 12, 1))
    impact = calculation_service.future_freizeitausgleich_impact(db, u, cutoff_date=CUTOFF, today=TODAY)
    assert float(impact) == 0.0


def test_weekend_overtime_skipped(db):
    u = _user(db)
    _overtime(db, u, date(2026, 12, 5))  # Samstag → 0 Soll
    impact = calculation_service.future_freizeitausgleich_impact(db, u, cutoff_date=CUTOFF, today=TODAY)
    assert float(impact) == 0.0


def test_fixed_monthly_target_user_zero(db):
    """#377 Baustein 2b: im Fix-Soll-Modus bewegt OVERTIME das Konto NICHT
    (OVERTIME ∉ _FIXED_*_TYPES) → kein künftiger Freizeitausgleich-Impact, sonst
    wäre die Projektion im Dezember nicht bitgleich zum dann tatsächlichen Saldo."""
    u = _user(db)
    u.milog_working_time_account = True
    u.agreed_monthly_hours = 80
    u.use_fixed_monthly_target = True
    db.commit()
    _overtime(db, u, date(2026, 12, 1))  # würde ohne Modus-Branch 8h liefern
    impact = calculation_service.future_freizeitausgleich_impact(db, u, cutoff_date=CUTOFF, today=TODAY)
    assert float(impact) == 0.0
