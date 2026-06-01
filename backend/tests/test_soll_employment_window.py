"""#193: Soll-/Überstundenberechnung muss Eintritts-/Austrittsdatum berücksichtigen.

Bisher iterierten get_monthly_target / get_overtime_account / get_ytd_summary über
alle Wochentage und addierten das Tagessoll OHNE first_work_day / last_work_day zu
prüfen → Soll für Zeiträume vor Eintritt bzw. nach Austritt (falsches Defizit).
Konsistenz zu get_vacation_account, das bereits pro-rata rechnet.

Reine Tages-Soll-Erwartung: 40h/5d = 8h pro Mon–Fri (kein Feiertag im Test-Tenant).
"""

from datetime import date, time, timedelta
from decimal import Decimal

from app.models import User, UserRole, YearCarryover, TimeEntry
from app.services import calculation_service
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID

DAILY = Decimal('8.00')  # 40h / 5 Tage


def _entry(db, user, d, start_h, end_h):
    e = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=time(start_h, 0), end_time=time(end_h, 0), break_minutes=0,
    )
    db.add(e)
    db.commit()
    return e


def _mk(db, username, **kw):
    defaults = dict(
        email=f"{username}@example.com", password_hash="h", first_name="E", last_name="U",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
        track_hours=True, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kw)
    u = User(username=username, **defaults)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _weekdays(start: date, end: date) -> int:
    n, c = 0, start
    while c <= end:
        if c.weekday() < 5:
            n += 1
        c += timedelta(days=1)
    return n


class TestMonthlyTargetEmploymentWindow:
    def test_month_entirely_before_first_work_day_is_zero(self, db, default_tenant):
        u = _mk(db, "starter", first_work_day=date(2026, 7, 1))
        assert calculation_service.get_monthly_target(db, u, 2026, 6) == Decimal('0.00')

    def test_month_entirely_after_last_work_day_is_zero(self, db, default_tenant):
        u = _mk(db, "leaver", last_work_day=date(2026, 6, 30))
        assert calculation_service.get_monthly_target(db, u, 2026, 7) == Decimal('0.00')

    def test_entry_mid_month_counts_only_from_first_work_day(self, db, default_tenant):
        u = _mk(db, "mid", first_work_day=date(2026, 7, 15))
        expected = (Decimal(_weekdays(date(2026, 7, 15), date(2026, 7, 31))) * DAILY).quantize(Decimal('0.01'))
        assert calculation_service.get_monthly_target(db, u, 2026, 7) == expected

    def test_full_month_when_started_before(self, db, default_tenant):
        u = _mk(db, "early", first_work_day=date(2026, 1, 1))
        expected = (Decimal(_weekdays(date(2026, 7, 1), date(2026, 7, 31))) * DAILY).quantize(Decimal('0.01'))
        assert calculation_service.get_monthly_target(db, u, 2026, 7) == expected


class TestYtdEmploymentWindow:
    def test_ytd_target_excludes_pre_employment_days(self, db, default_tenant):
        u = _mk(db, "ytd", first_work_day=date(2026, 4, 1))
        end = today_local() if today_local().year == 2026 else date(2026, 12, 31)
        # Only days from first_work_day onward (and not in the future) count.
        window_end = min(end, date(2026, 12, 31))
        expected = float((Decimal(_weekdays(date(2026, 4, 1), window_end)) * DAILY).quantize(Decimal('0.01')))
        ytd = calculation_service.get_ytd_summary(db, u, 2026)
        assert ytd["target_hours"] == expected


class TestOvertimeAccountEmploymentWindow:
    def test_overtime_account_excludes_pre_employment_months(self, db, default_tenant):
        # A YearCarryover forces the cumulative loop to start in January; the
        # pre-employment months (Jan–Jun) must add 0 target -> the only deficit
        # is July's target (no time entries).
        u = _mk(db, "ot", first_work_day=date(2026, 7, 1))
        db.add(YearCarryover(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                             overtime_hours=0, vacation_days=0))
        db.commit()
        bal = calculation_service.get_overtime_account(db, u, 2026, 7)
        expected = (Decimal('0') - Decimal(_weekdays(date(2026, 7, 1), date(2026, 7, 31))) * DAILY).quantize(Decimal('0.01'))
        assert bal == expected


class TestActualRespectsEmploymentWindow:
    """#195: die Ist-Seite (TimeEntry + credited SICK/TRAINING) darf Tage
    außerhalb des Beschäftigungsfensters nicht mitzählen — sonst Phantom-Überstunden."""

    def test_monthly_actual_excludes_pre_employment_entry(self, db, default_tenant):
        u = _mk(db, "act1", first_work_day=date(2026, 7, 1))
        _entry(db, u, date(2026, 6, 10), 8, 16)  # vor Eintritt (Rehire/Import)
        assert calculation_service.get_monthly_actual(db, u, 2026, 6) == Decimal('0.00')

    def test_monthly_actual_includes_in_window_entry(self, db, default_tenant):
        u = _mk(db, "act2", first_work_day=date(2026, 7, 1))
        _entry(db, u, date(2026, 7, 1), 8, 16)  # im Fenster
        assert calculation_service.get_monthly_actual(db, u, 2026, 7) == Decimal('8.00')

    def test_overtime_account_excludes_pre_employment_actual(self, db, default_tenant):
        u = _mk(db, "act3", first_work_day=date(2026, 7, 1))
        _entry(db, u, date(2026, 6, 10), 8, 16)  # vor Eintritt → darf NICHT als Ist zählen
        bal = calculation_service.get_overtime_account(db, u, 2026, 7)
        july_target = Decimal(_weekdays(date(2026, 7, 1), date(2026, 7, 31))) * DAILY
        # Nur Juli-Soll als Defizit; das Juni-Ist trägt nichts bei.
        assert bal == (Decimal('0') - july_target).quantize(Decimal('0.01'))

    def test_balance_sum_equals_overtime_account(self, db, default_tenant):
        u = _mk(db, "act4", first_work_day=date(2026, 7, 1))
        _entry(db, u, date(2026, 6, 10), 8, 16)  # außerhalb
        _entry(db, u, date(2026, 7, 1), 8, 16)   # innerhalb
        jun = calculation_service.get_monthly_balance(db, u, 2026, 6)
        jul = calculation_service.get_monthly_balance(db, u, 2026, 7)
        oa = calculation_service.get_overtime_account(db, u, 2026, 7)
        assert (jun + jul) == oa  # Konsistenz Σ Monatssaldo == Überstundenkonto

    def test_ytd_actual_excludes_pre_employment_entry(self, db, default_tenant):
        # today=2026-06-01; Eintritt 01.05., Eintrag 10.04. (vor Eintritt, vor heute).
        u = _mk(db, "act5", first_work_day=date(2026, 5, 1))
        _entry(db, u, date(2026, 4, 10), 8, 16)
        ytd = calculation_service.get_ytd_summary(db, u, 2026)
        assert ytd["actual_hours"] == 0.0  # Vor-Eintritts-Ist zählt nicht
