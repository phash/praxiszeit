"""Fix #1: Halbtags-Abwesenheit (VACATION/OTHER/PAID_LEAVE mit half_day=True)
reduziert das Soll nur um 0,5 × Tagessoll — NICHT um das ganze Tagessoll.

Vorher übersprangen alle vier Soll-Per-Tag-Schleifen den ganzen Tag (reine
Datums-Mengen-Mitgliedschaft), sodass ein Halbtags-Urlaub den Tag soll-frei
machte → Phantom-Überstunden bei Arbeit der zweiten Hälfte, und ein ganzer
freier Tag kostete nur 0,5 Urlaubstage. Jetzt bleibt die nicht-freie Hälfte
als Soll bestehen (gemeinsamer Per-Tag-Helper für alle vier Schleifen).
"""
from decimal import Decimal
from datetime import date, time

from app.models import Absence, AbsenceType, TimeEntry
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID

# 2026-03-09 = Montag … 2026-03-13 = Freitag (saubere Woche ohne Feiertage)
MON, TUE, WED, THU, FRI = (
    date(2026, 3, 9), date(2026, 3, 10), date(2026, 3, 11),
    date(2026, 3, 12), date(2026, 3, 13),
)


def _entry(db, user, d, start_h, end_h, break_min=0):
    e = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=time(start_h, 0), end_time=time(end_h, 0), break_minutes=break_min,
    )
    db.add(e)
    db.commit()
    return e


def _absence(db, user, d, absence_type, hours, half_day):
    a = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        type=absence_type, hours=hours, half_day=half_day,
    )
    db.add(a)
    db.commit()
    return a


def test_half_day_vacation_plus_morning_work_balance_zero(db, test_user):
    """8h/Tag-MA: Mo Halbtags-VACATION + 4h vormittags gearbeitet, Di–Fr je 8h.
    Soll = 4h(Mo) + 32h = 36h; Ist = 4h + 32h = 36h → Saldo 0 (nicht +4h)."""
    _absence(db, test_user, MON, AbsenceType.VACATION, 4.0, half_day=True)
    _entry(db, test_user, MON, 8, 12)  # 4h vormittags
    for d in (TUE, WED, THU, FRI):
        _entry(db, test_user, d, 8, 16)  # 8h

    target = calculation_service.get_range_target(db, test_user, MON, FRI)
    actual = calculation_service.get_range_actual(db, test_user, MON, FRI)
    assert target == Decimal('36.00'), target
    assert actual == Decimal('36.00'), actual
    assert (actual - target) == Decimal('0.00')


def test_pure_half_day_vacation_keeps_half_target(db, test_user):
    """Reiner Halbtags-Urlaub ohne Arbeit: 0,5 × Tagessoll (4h) bleibt Soll."""
    _absence(db, test_user, MON, AbsenceType.VACATION, 4.0, half_day=True)
    target = calculation_service.get_range_target(db, test_user, MON, MON)
    assert target == Decimal('4.00'), target


def test_full_day_vacation_still_removes_whole_target(db, test_user):
    """Regression: Voll-Tag-Urlaub (half_day=False) entfernt weiter das ganze Soll."""
    _absence(db, test_user, MON, AbsenceType.VACATION, 8.0, half_day=False)
    target = calculation_service.get_range_target(db, test_user, MON, MON)
    assert target == Decimal('0.00'), target


def test_legacy_null_half_day_treated_as_full(db, test_user):
    """Legacy-Row (half_day=None, vor dem Feld) bleibt Voll-Skip — keine Regression."""
    _absence(db, test_user, MON, AbsenceType.VACATION, 8.0, half_day=None)
    target = calculation_service.get_range_target(db, test_user, MON, MON)
    assert target == Decimal('0.00'), target


def test_half_day_in_overtime_account(db, test_user):
    """Das Halbtags-Soll greift auch im Überstundenkonto (zweite Soll-Schleife):
    an einem Tag OHNE erfasste Arbeitszeit entfernt der Voll-Tag 8h Soll, der
    Halbtag nur 4h → Halbtag-Konto ist 4h niedriger.

    F1 (1.18.0): liegt am selben Tag ein Zeiteintrag, gilt dieser Kontrast NICHT
    mehr — eine Ganztags-Abwesenheit streicht dort nur noch den nicht
    gearbeiteten Teil (min(Tagessoll, gearbeitete Stunden) bleibt Soll), sonst
    stünde die gearbeitete Zeit als Phantom-Überstunde im Konto. Beide Fälle
    werden hier geprüft.
    """
    _absence(db, test_user, MON, AbsenceType.VACATION, 4.0, half_day=True)
    _entry(db, test_user, MON, 8, 12)  # 4h vormittags
    for d in (TUE, WED, THU, FRI):
        _entry(db, test_user, d, 8, 16)
    acct_half = calculation_service.get_overtime_account(db, test_user, 2026, 3)

    a = db.query(Absence).filter(Absence.user_id == test_user.id, Absence.date == MON).one()
    a.half_day = False
    a.hours = 8.0
    db.commit()
    acct_full = calculation_service.get_overtime_account(db, test_user, 2026, 3)

    # F1: mit den 4 gestempelten Stunden bleibt in BEIDEN Fällen 4h Soll stehen.
    assert acct_full == acct_half, (acct_full, acct_half)

    # Ohne Zeiteintrag am Montag bleibt der ursprüngliche Kontrast bestehen.
    db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id,
                               TimeEntry.date == MON).delete()
    db.commit()
    acct_full_no_entry = calculation_service.get_overtime_account(db, test_user, 2026, 3)
    a.half_day = True
    a.hours = 4.0
    db.commit()
    acct_half_no_entry = calculation_service.get_overtime_account(db, test_user, 2026, 3)
    assert (acct_full_no_entry - acct_half_no_entry) == Decimal('4.00'), (
        acct_full_no_entry, acct_half_no_entry)


def test_half_day_history_matches_account(db, test_user):
    """get_overtime_history bleibt bitgleich zu get_overtime_account auch mit Halbtag."""
    _absence(db, test_user, MON, AbsenceType.VACATION, 4.0, half_day=True)
    _entry(db, test_user, MON, 8, 12)
    for d in (TUE, WED, THU, FRI):
        _entry(db, test_user, d, 8, 16)
    acct = calculation_service.get_overtime_account(db, test_user, 2026, 3)
    hist = calculation_service.get_overtime_history(db, test_user, 2026, 3)
    assert hist[(2026, 3)] == acct, (hist.get((2026, 3)), acct)


def test_half_day_in_ytd_summary(db, test_user):
    """Das Halbtags-Soll greift auch im YTD-Summary (vierte Soll-Schleife)."""
    _absence(db, test_user, MON, AbsenceType.VACATION, 4.0, half_day=True)
    ytd_half = calculation_service.get_ytd_summary(db, test_user, 2026)

    a = db.query(Absence).filter(Absence.user_id == test_user.id, Absence.date == MON).one()
    a.half_day = False
    a.hours = 8.0
    db.commit()
    ytd_full = calculation_service.get_ytd_summary(db, test_user, 2026)

    # Voll-Tag entfernt 8h Soll, Halbtag nur 4h → Halbtag-Soll ist 4h höher.
    assert round(ytd_half["target_hours"] - ytd_full["target_hours"], 2) == 4.0
