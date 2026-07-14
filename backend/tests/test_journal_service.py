"""Tests für journal_service."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import TimeEntry, Absence, AbsenceType, PublicHoliday
from app.services import journal_service, calculation_service
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


def test_journal_day_actuals_windowed_match_monthly_actual(db, test_user):
    """#198: Ein TimeEntry VOR first_work_day darf das Tages-Ist nicht aufblaehen.
    Summe der Tageszeilen muss dem (gefensterten) Monats-Ist entsprechen."""
    test_user.first_work_day = date(2026, 3, 16)  # Eintritt Mitte Maerz
    db.commit()
    _make_entry(db, test_user, date(2026, 3, 9), 8, 16)    # Mo, VOR Eintritt (out-of-window)
    _make_entry(db, test_user, date(2026, 3, 23), 8, 16)   # Mo, nach Eintritt (zaehlt)

    result = journal_service.get_journal(db, test_user, 2026, 3)
    sum_day_actual = round(sum(d["actual_hours"] for d in result["days"]), 2)
    monthly_actual = round(float(calculation_service.get_monthly_actual(db, test_user, 2026, 3)), 2)
    assert sum_day_actual == monthly_actual

    mar9 = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert mar9["actual_hours"] == 0.0   # out-of-window -> kein Ist
    mar23 = next(d for d in result["days"] if d["date"] == "2026-03-23")
    assert mar23["actual_hours"] == 8.0  # in-window -> zaehlt


def test_journal_paid_leave_day_type(db, test_user):
    # Fix: PAID_LEAVE war nicht in _ABSENCE_TYPE_MAP → wurde als "other" typisiert.
    _make_absence(db, test_user, date(2026, 3, 4), AbsenceType.PAID_LEAVE)
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-04")
    assert day["type"] == "paid_leave"


def test_journal_masks_custom_reason_absence_without_health_data(db, test_user):
    # #312/#376 DSGVO: eine Absence mit reason_id (z. B. Kind krank) muss ohne
    # angeforderte Gesundheitsdaten maskiert werden (Tagestyp + Label → "absent").
    from app.models import AbsenceReason
    r = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Kind krank",
                      base_behavior="unpaid_free", is_active=True, tracks_child_sick_limit=True)
    db.add(r); db.commit(); db.refresh(r)
    a = Absence(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=date(2026, 3, 5),
                type=AbsenceType.OTHER, hours=Decimal("8"), reason_id=r.id)
    db.add(a); db.commit()

    masked = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=False)
    day_m = next(d for d in masked["days"] if d["date"] == "2026-03-05")
    assert day_m["type"] == "absent"
    assert day_m["absences"][0]["type"] == "absent"
    assert "Kind krank" not in str(day_m)

    shown = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=True)
    day_s = next(d for d in shown["days"] if d["date"] == "2026-03-05")
    assert day_s["absences"][0]["type"] == "Kind krank"  # eigener Grund-Name sichtbar


def test_journal_renders_without_error_for_fixed_mode_user(db, default_tenant):
    """Finding 3 (Whole-Branch-Review, #377 Baustein 2b): ein Fix-Modus-MA
    (use_fixed_monthly_target) darf im Journal weder crashen noch eine
    irreführende Kumulierung zeigen. Die Tageszeilen bleiben bewusst die
    GEPLANTE Anwesenheit (kein Per-Tag-Zerlegen des flachen Monats-Solls,
    siehe Kommentar bei _eff_daily_target) — die maßgebliche Soll/Ist/Saldo-
    Zahl ist monthly_summary (modus-bewusst über get_monthly_target/actual)."""
    from tests.test_fixed_monthly_target import _mk

    u = _mk(db)  # agreed=40h fix, Mo+Mi geplant à 3h
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                     start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()

    result = journal_service.get_journal(db, u, 2025, 3)  # no crash
    assert len(result["days"]) == 31

    expected_target = calculation_service.get_monthly_target(db, u, 2025, 3)
    expected_actual = calculation_service.get_monthly_actual(db, u, 2025, 3)
    assert result["monthly_summary"]["target_hours"] == pytest.approx(float(expected_target))
    assert result["monthly_summary"]["actual_hours"] == pytest.approx(float(expected_actual))
    assert result["monthly_summary"]["balance"] == pytest.approx(
        float(expected_actual - expected_target))

    # Bewusst KEINE Assertion, dass Σ(day["target_hours"]) == monthly_summary
    # (Finding 3: erwartete Divergenz bei fixem Monats-Soll, kein Bug).
