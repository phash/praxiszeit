"""Tests für journal_service."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import TimeEntry, Absence, AbsenceType, PublicHoliday
from app.services import journal_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_entry(db, user, d, start_h, end_h, break_min=0):
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        start_time=time(start_h, 0),
        end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _make_absence(db, user, d, atype, hours=8.0):
    absence = Absence(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        type=atype,
        hours=hours,
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)
    return absence


def test_journal_returns_correct_day_count(db, test_user):
    """Prüft dass das Journal exakt so viele Tage enthält wie der Monat hat — Grundlage für lückenlose Monatsansicht."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert len(result["days"]) == 31


def test_journal_work_day_has_correct_type(db, test_user):
    """Prüft dass ein Werktag mit Zeiteintrag als 'work' klassifiziert wird und die Ist-Stunden stimmen."""
    monday = date(2026, 3, 9)
    _make_entry(db, test_user, monday, 8, 17, break_min=60)
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert day["type"] == "work"
    assert day["actual_hours"] == pytest.approx(8.0)


def test_journal_weekend_has_weekend_type(db, test_user):
    """Prüft dass Wochenendtage als 'weekend' mit 0h Soll markiert werden — keine Fehlberechnung am Wochenende."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-14")
    assert day["type"] == "weekend"
    assert day["actual_hours"] == 0.0
    assert day["target_hours"] == 0.0


def test_journal_holiday_has_holiday_type(db, test_user):
    """Prüft dass Feiertage als 'holiday' mit Name und 0h Soll angezeigt werden — kein Defizit an Feiertagen."""
    h = PublicHoliday(date=date(2026, 3, 11), name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID)
    db.add(h)
    db.commit()
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-11")
    assert day["type"] == "holiday"
    assert day["holiday_name"] == "Testfeiertag"
    assert day["target_hours"] == 0.0


def test_journal_vacation_day(db, test_user):
    """Prüft dass Urlaubstage als 'vacation' mit ausgeglichenem Saldo erscheinen — Urlaub erzeugt kein Defizit."""
    tuesday = date(2026, 3, 10)
    _make_absence(db, test_user, tuesday, AbsenceType.VACATION, hours=8.0)
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-10")
    assert day["type"] == "vacation"
    assert day["target_hours"] == 8.0  # target = absence_sum so balance = 0
    assert day["balance"] == 0.0


def test_journal_empty_work_day_is_deficit(db, test_user):
    """Prüft dass ein Werktag ohne Zeiteintrag als 'empty' mit negativem Saldo erscheint — Fehlstunden sichtbar."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    monday = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert monday["type"] == "empty"
    assert monday["actual_hours"] == 0.0
    assert monday["target_hours"] == pytest.approx(8.0)
    assert monday["balance"] == pytest.approx(-8.0)


def test_journal_monthly_summary(db, test_user):
    """Prüft dass die Monatsübersicht konsistent mit dem calculation_service berechnet wird — keine Abweichungen."""
    from app.services import calculation_service
    result = journal_service.get_journal(db, test_user, 2026, 3)
    expected_target = float(calculation_service.get_monthly_target(db, test_user, 2026, 3))
    assert result["monthly_summary"]["target_hours"] == pytest.approx(expected_target)


def test_journal_yearly_overtime_zero_without_entries(db, test_user):
    """Prüft dass ohne Zeiteinträge die Jahresüberstunden 0 sind — sauberer Ausgangszustand."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert result["yearly_overtime"] == 0.0


def test_journal_user_info_included(db, test_user):
    """Prüft dass Benutzerinfos im Journal enthalten sind — Frontend braucht Name für die Anzeige."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert result["user"]["first_name"] == test_user.first_name
    assert result["user"]["last_name"] == test_user.last_name
