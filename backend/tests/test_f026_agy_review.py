"""F-026-Nachzug aus dem externen Zweit-Review (agy, 2026-10-17).

Die Projektregel F-026 verlangt an jeder Abfrage auf eine mandantengebundene
Tabelle einen expliziten ``tenant_id``-Filter zusaetzlich zu RLS. Folgende
Lesestellen filterten nur nach ``user_id``:

- ``reports.py``: Sonntagsarbeit (§11), Nachtarbeit (§6), Ersatzruhetage (§11)
- ``rest_time_service.check_rest_time_violations`` (§5)
- ``auth.py`` ``GET /me/export`` (Art. 20 DSGVO): Zeiteintraege + Abwesenheiten
- ``calculation_service``: die in CLAUDE.md als Restschuld gefuehrten
  ``TimeEntry``-/``YearCarryover``-Abfragen in ``get_overtime_account``,
  ``get_overtime_history_detailed``, ``get_ytd_summary``, dazu
  ``get_range_actual``, ``get_monthly_worked_hours`` und ``get_vacation_account``

Wie in ``test_audit_20260731_nachzuege.py``: Die SQLite-Suite kennt kein RLS.
Eine Zeile, die auf dieselbe ``user_id`` zeigt, aber die ``tenant_id`` eines
fremden Mandanten traegt, wird von einer korrekt gefilterten Abfrage nicht
gesehen. Jeder Test vergleicht gegen eine baugleiche Kontrollperson ohne
Fremdzeilen, damit ein zu scharfer Filter ebenfalls auffaellt.
"""
import json
import uuid
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import Absence, AbsenceType, TimeEntry, User, UserRole
from app.models.tenant import Tenant
from app.models.year_carryover import YearCarryover
from app.routers.auth import export_my_data
from app.routers.reports import (
    get_compensatory_rest, get_night_work_summary, get_sunday_summary,
)
from app.services import calculation_service
from app.services.rest_time_service import check_rest_time_violations
from tests.conftest import DEFAULT_TENANT_ID

FOREIGN_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fe")

# Maerz 2026: 01.03. = Sonntag, 02.03. = Montag, 03.03. = Dienstag.
SUNDAY = date(2026, 3, 1)
MONDAY = date(2026, 3, 2)
TUESDAY = date(2026, 3, 3)
WEDNESDAY = date(2026, 3, 4)


@pytest.fixture
def foreign_tenant(db, default_tenant):
    t = Tenant(id=FOREIGN_TENANT_ID, name="Fremd AG", slug="fremd-agy",
               is_active=True, mode="multi")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, role=UserRole.EMPLOYEE):
    u = User(
        username=username, email=f"{username}@x.de", password_hash="h",
        first_name=username, last_name="T", role=role, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        track_hours=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _entry(db, user, d, start, end, tenant_id=DEFAULT_TENANT_ID):
    e = TimeEntry(user_id=user.id, tenant_id=tenant_id, date=d,
                  start_time=start, end_time=end, break_minutes=0)
    db.add(e)
    db.commit()
    return e


def _person(db, username, with_foreign):
    """Eigener 8-h-Tag am Montag; optional Fremdzeilen desselben user_id."""
    user = _make_user(db, username)
    _entry(db, user, MONDAY, time(9, 0), time(17, 0))
    if with_foreign:
        f = FOREIGN_TENANT_ID
        _entry(db, user, SUNDAY, time(9, 0), time(13, 0), tenant_id=f)
        # 00:30–05:30: Nachtarbeit (> 2 h zwischen 23 und 6 Uhr) und nur
        # 7,5 h Ruhe nach dem Montagsende 17:00 (§5)
        _entry(db, user, TUESDAY, time(0, 30), time(5, 30), tenant_id=f)
        _entry(db, user, WEDNESDAY, time(9, 0), time(17, 0), tenant_id=f)
        db.add(Absence(user_id=user.id, tenant_id=f, date=date(2026, 3, 5),
                       type=AbsenceType.VACATION, hours=8.0))
        db.add(YearCarryover(user_id=user.id, tenant_id=f, year=2026,
                             overtime_hours=Decimal("50"),
                             vacation_days=Decimal("10"), source="manual"))
        db.commit()
    return user


@pytest.fixture
def pair(db, foreign_tenant):
    return _person(db, "agy_user", True), _person(db, "agy_ctl", False)


# --------------------------------------------------------------------------
# calculation_service
# --------------------------------------------------------------------------

def test_range_actual_ignores_foreign_entries(db, pair):
    user, ctl = pair
    start, end = date(2026, 3, 1), date(2026, 3, 31)
    assert (calculation_service.get_range_actual(db, user, start, end)
            == calculation_service.get_range_actual(db, ctl, start, end) == 8)


def test_monthly_worked_hours_ignores_foreign_entries(db, pair):
    user, ctl = pair
    assert (calculation_service.get_monthly_worked_hours(db, user, 2026, 3)
            == calculation_service.get_monthly_worked_hours(db, ctl, 2026, 3))


def test_overtime_account_ignores_foreign_rows(db, pair):
    """Fremder Zeiteintrag, fremder Uebertrag (+50 h), fremder Urlaub."""
    user, ctl = pair
    assert (calculation_service.get_overtime_account(db, user, 2026, 3)
            == calculation_service.get_overtime_account(db, ctl, 2026, 3))


def test_overtime_history_detailed_ignores_foreign_rows(db, pair):
    user, ctl = pair
    hist = calculation_service.get_overtime_history_detailed(db, user, 2026, 3)
    ctl_hist = calculation_service.get_overtime_history_detailed(db, ctl, 2026, 3)
    assert sorted(hist) == sorted(ctl_hist)
    for key in ctl_hist:
        assert hist[key].actual == ctl_hist[key].actual
        assert hist[key].target == ctl_hist[key].target
    assert (calculation_service.get_overtime_account(db, user, 2026, 3)
            == calculation_service.get_overtime_account(db, ctl, 2026, 3))


def test_ytd_summary_ignores_foreign_rows(db, pair):
    user, ctl = pair
    assert (calculation_service.get_ytd_summary(db, user, 2026)
            == calculation_service.get_ytd_summary(db, ctl, 2026))


def test_vacation_account_ignores_foreign_rows(db, pair):
    """Fremder Urlaubstag und fremder Urlaubsuebertrag (+10 Tage)."""
    user, ctl = pair
    acc = calculation_service.get_vacation_account(db, user, 2026)
    ctl_acc = calculation_service.get_vacation_account(db, ctl, 2026)
    for key in ("budget_days", "used_days", "remaining_days"):
        assert acc[key] == ctl_acc[key], key


# --------------------------------------------------------------------------
# §5 Ruhezeit
# --------------------------------------------------------------------------

def test_rest_time_ignores_foreign_entries(db, pair):
    user, ctl = pair
    assert check_rest_time_violations(db, user, 2026, 3) == []
    assert check_rest_time_violations(db, ctl, 2026, 3) == []


# --------------------------------------------------------------------------
# Admin-Berichte (§6, §11)
# --------------------------------------------------------------------------

def _row(report, user):
    return next(r for r in report["employees"] if r["user_id"] == str(user.id))


@pytest.fixture
def admin(db, foreign_tenant):
    return _make_user(db, "agy_admin", role=UserRole.ADMIN)


def test_sunday_summary_ignores_foreign_entries(db, pair, admin):
    user, _ = pair
    report = get_sunday_summary(year=2026, db=db, current_user=admin)
    assert _row(report, user)["sundays_worked"] == 0


def test_night_work_summary_ignores_foreign_entries(db, pair, admin):
    user, _ = pair
    report = get_night_work_summary(year=2026, db=db, current_user=admin)
    assert _row(report, user)["night_work_days"] == 0


def test_compensatory_rest_ignores_foreign_entries(db, pair, admin):
    user, _ = pair
    report = get_compensatory_rest(year=2026, db=db, current_user=admin)
    assert _row(report, user)["sunday_holiday_days_worked"] == 0


# --------------------------------------------------------------------------
# Art. 20 DSGVO
# --------------------------------------------------------------------------

def test_me_export_ignores_foreign_rows(db, pair):
    user, _ = pair
    data = json.loads(export_my_data(current_user=user, db=db).body)
    assert [e["date"] for e in data["zeiteintraege"]] == [str(MONDAY)]
    assert data["abwesenheiten"] == []
