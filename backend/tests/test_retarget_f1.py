"""Spec 9.6 (E51, P27): F1-Klemmung in retarget_absence_hours und Wirkungsfenster
mit Zeiteinträgen (9.1). Tabelle 9.6: Tagessoll vorher 8 h, 4 h Arbeit am Krank-Tag."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import AbsenceType
from app.models.system_setting import SystemSetting
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import absence, add_row, entry, freeze, t

MON = date(2026, 9, 14)
WINDOW = (date(2026, 9, 1), date(2026, 9, 30))
OLD = {MON: Decimal("8")}


def _run(db, user, old=OLD):
    return cs.retarget_absence_hours(db, user, *WINDOW, old_full_target_by_date=old)


def _day_saldo(db, user, d):
    return cs.get_range_actual(db, user, d, d) - cs.get_range_target(db, user, d, d)


def test_regular_clamped_mixed_day_with_target_drop_is_not_a_reduction(db, test_user):
    a = absence(db, test_user, MON, AbsenceType.SICK, 4.0)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
    [rec] = _run(db, test_user)
    assert (rec.old_hours, rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (
        Decimal("4.00"), Decimal("2.00"), True, False)
    db.refresh(a)
    assert float(a.hours) == 2.0


def test_double_credit_before_1_18_with_unchanged_target_is_a_reduction(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    [rec] = _run(db, test_user)
    assert (rec.old_hours, rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (
        Decimal("8.00"), Decimal("4.00"), True, True)


def test_double_credit_with_target_drop_is_a_reduction(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
    [rec] = _run(db, test_user)
    assert (rec.new_hours, rec.credit_reduction) == (Decimal("2.00"), True)


def test_entry_gaining_on_a_mixed_day_reduces_the_credit(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 4.0)
    entry(db, test_user, MON, t(8), t(13), grace=None)   # nach der Neukappung 5 h Arbeit
    [rec] = _run(db, test_user)
    assert (rec.old_hours, rec.new_hours, rec.credit_reduction) == (Decimal("4.00"), Decimal("3.00"), True)


def test_already_clamped_and_unchanged_is_not_returned(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 4.0)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    assert _run(db, test_user) == []


def test_rounding_to_0_01_hours(db, test_user):
    """Tagessoll 7,92 h: (2 − 3,92) gegen (6 − 7,92) — beide −1,92."""
    add_row(db, test_user, date(2026, 1, 1), day_hours=(7.92, 8, 8, 8, 8))
    absence(db, test_user, MON, AbsenceType.SICK, 3.92)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    add_row(db, test_user, date(2026, 9, 1), day_hours=(6, 8, 8, 8, 8))
    [rec] = _run(db, test_user, {MON: Decimal("7.92")})
    assert (rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (Decimal("2.00"), True, False)


@pytest.mark.parametrize("typ, reduction", [
    (AbsenceType.SICK, True),
    (AbsenceType.TRAINING, True),
    (AbsenceType.VACATION, False),
    (AbsenceType.PAID_LEAVE, False),
    (AbsenceType.OTHER, False),
])
def test_only_actual_credits_can_be_reduced(db, test_user, typ, reduction):
    """9.5 (c) meint die IST-Gutschrift (P27: „nehmen gutgeschriebene Zeit
    zurück") — die tragen nur SICK/TRAINING (``credited_absence_hours``). Bei
    VACATION/PAID_LEAVE/OTHER fällt das Soll auf ``min(Tagessoll, gearbeitet)``,
    unabhängig von ``hours`` (#377-Fix-Modus: geplante Stunden): die F1-
    Angleichung an den nicht gearbeiteten Rest bleibt (wie ``create_absence``),
    kostet aber kein Saldo und ist deshalb keine Verkürzung (Review Task 6)."""
    absence(db, test_user, MON, typ, 8.0)
    entry(db, test_user, MON, t(8), t(10), grace=None)
    saldo_before = _day_saldo(db, test_user, MON)
    [rec] = _run(db, test_user)
    assert (rec.old_hours, rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (
        Decimal("8.00"), Decimal("6.00"), True, reduction)
    assert (_day_saldo(db, test_user, MON) < saldo_before) is reduction


def test_sick_day_without_work_follows_the_target(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
    [rec] = _run(db, test_user)
    assert (rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (Decimal("6.00"), False, False)


def test_open_entries_do_not_count_as_kept_work(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    entry(db, test_user, MON, t(8), None, grace=None)
    assert _run(db, test_user) == []


def test_half_special_day_stays_saldo_neutral(db, test_user):
    """Spec 9.6: 24.12. halber Sondertag + Krank + 3 h Arbeit, Tagessoll 8 →
    Soll 4 h, Gutschrift höchstens 1 h, Saldo des Tages 0."""
    xmas = date(2026, 12, 24)
    db.add(SystemSetting(key="special_day_dec24_mode", value="half_day", tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    absence(db, test_user, xmas, AbsenceType.SICK, 8.0)
    entry(db, test_user, xmas, t(8), t(11), grace=None)
    [rec] = cs.retarget_absence_hours(db, test_user, date(2026, 12, 1), date(2026, 12, 31),
                                      old_full_target_by_date={xmas: Decimal("8")})
    assert rec.new_hours == Decimal("2.00")   # × Gewicht 0,5 = 1 h Gutschrift
    saldo = cs.get_range_actual(db, test_user, xmas, xmas) - cs.get_range_target(db, test_user, xmas, xmas)
    assert saldo == Decimal("0")


def test_absence_full_targets_skips_overtime(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    absence(db, test_user, MON + timedelta(days=1), AbsenceType.OVERTIME, 8.0)
    assert cs.absence_full_targets(db, test_user, *WINDOW) == {MON: Decimal("8")}


def test_retarget_window_knows_time_entries(db, test_user, monkeypatch):
    freeze(monkeypatch)
    future = date(2026, 10, 20)
    entry(db, test_user, future, t(8), t(12), grace=None)
    w = cs.retarget_window(db, test_user, date(2026, 9, 1))
    assert (w.last_time_entry, w.has_time_entries, w.end) == (future, True, future)
    add_row(db, test_user, date(2026, 10, 12), weekly_hours=30)
    w = cs.retarget_window(db, test_user, date(2026, 9, 1))
    assert (w.last_time_entry, w.has_time_entries, w.end) == (None, False, date(2026, 10, 11))
