"""Rückrechnung der Abwesenheits-Stunden nach einer Wochenstunden-Änderung.

Das Soll rechnet datumsbasiert automatisch neu (``get_weekly_hours_for_date``).
Die beim Buchen festgeschriebenen ``Absence.hours`` tun das NICHT — ein Krankentag
würde nach einer rückwirkenden Umstellung von 40 auf 20 h/Woche weiterhin 8 h
gutschreiben, während das Soll desselben Tages nur noch 4 h beträgt. Soll und Ist
widersprächen sich im selben Monat.

``retarget_absence_hours`` zieht die Stunden nach. Es ist die EINZIGE Stelle, die
das tut — Anlegen, Löschen und die Vorschau rufen alle hier hinein.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models import Absence, AbsenceType, PublicHoliday, WorkingHoursChange
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


# 2026-03-09 = Montag, 03-14 = Samstag, 03-15 = Sonntag
MON = date(2026, 3, 9)
TUE = date(2026, 3, 10)
WED = date(2026, 3, 11)
SAT = date(2026, 3, 14)
WINDOW = (date(2026, 3, 1), date(2026, 3, 31))


def _absence(db, user, d, typ=AbsenceType.VACATION, hours=8.0, half_day=False):
    a = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        type=typ, hours=hours, half_day=half_day,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


def _halve_hours(db, user, effective_from=date(2026, 3, 1), weekly=20.0):
    """Wochenstunden ab ``effective_from`` halbieren (40 → 20 ⇒ Tagessoll 8 → 4)."""
    db.add(WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=effective_from, weekly_hours=Decimal(str(weekly)),
    ))
    db.commit()


def _run(db, user, dry_run=False):
    return calculation_service.retarget_absence_hours(
        db, user, WINDOW[0], WINDOW[1], dry_run=dry_run
    )


class TestAdjustsWhatItShould:
    def test_vacation_hours_follow_the_new_daily_target(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 1
        db.refresh(a)
        assert float(a.hours) == 4.0

    def test_vacation_days_stay_unchanged(self, db, test_user):
        """Tagesprinzip (§3 BUrlG): 1 freier Arbeitstag = 1 Urlaubstag, unabhängig
        von den Stunden. Die Rückrechnung darf den Tage-Verbrauch NICHT bewegen."""
        _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)
        before = calculation_service.get_vacation_account(db, test_user, 2026)["used_days"]

        _run(db, test_user)
        db.expire_all()
        after = calculation_service.get_vacation_account(db, test_user, 2026)["used_days"]
        assert float(after) == float(before) == 1.0

    def test_sick_and_training_are_adjusted(self, db, test_user):
        """Bei diesen beiden ist `hours` die Ist-Gutschrift — bleibt sie stehen,
        weist der Monat mehr Ist als Soll aus."""
        sick = _absence(db, test_user, MON, AbsenceType.SICK, 8.0)
        training = _absence(db, test_user, TUE, AbsenceType.TRAINING, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 2
        db.refresh(sick); db.refresh(training)
        assert float(sick.hours) == 4.0
        assert float(training.hours) == 4.0

    def test_half_day_gets_half_the_target(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 4.0, half_day=True)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 1
        db.refresh(a)
        assert float(a.hours) == 2.0

    def test_paid_leave_and_other_are_adjusted(self, db, test_user):
        pl = _absence(db, test_user, MON, AbsenceType.PAID_LEAVE, 8.0)
        other = _absence(db, test_user, TUE, AbsenceType.OTHER, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 2
        db.refresh(pl); db.refresh(other)
        assert float(pl.hours) == 4.0 and float(other.hours) == 4.0


class TestLeavesAloneWhatItShould:
    def test_overtime_is_never_touched(self, db, test_user):
        """Freizeitausgleich trägt explizit beantragte Stunden, kein abgeleitetes
        Tagessoll — CLAUDE.md: Soll bleibt, Ist = 0."""
        a = _absence(db, test_user, MON, AbsenceType.OVERTIME, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_untracked_user_is_untouched(self, db, test_user):
        """track_hours=False (leitende Angestellte): dort zählt nur die
        Tageszählung, Stunden sind Rauschen."""
        test_user.track_hours = False
        db.commit()
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_weekend_is_skipped(self, db, test_user):
        a = _absence(db, test_user, SAT, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_public_holiday_is_skipped(self, db, test_user):
        db.add(PublicHoliday(
            date=WED, name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID,
        ))
        db.commit()
        a = _absence(db, test_user, WED, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_absence_before_first_work_day_untouched(self, db, test_user):
        test_user.first_work_day = date(2026, 3, 20)
        db.commit()
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_absence_after_last_work_day_untouched(self, db, test_user):
        test_user.last_work_day = date(2026, 3, 5)
        db.commit()
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_absence_outside_the_window_untouched(self, db, test_user):
        a = _absence(db, test_user, date(2026, 2, 9), AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user, effective_from=date(2026, 1, 1))

        assert _run(db, test_user) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_already_correct_hours_are_not_counted(self, db, test_user):
        """Idempotenz: ein zweiter Lauf darf nichts mehr melden."""
        _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user) == 1
        assert _run(db, test_user) == 0


class TestDryRun:
    def test_dry_run_counts_but_changes_nothing(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert _run(db, test_user, dry_run=True) == 1
        db.refresh(a)
        assert float(a.hours) == 8.0, "dry_run darf nicht schreiben"

    def test_empty_window_returns_zero(self, db, test_user):
        assert calculation_service.retarget_absence_hours(
            db, test_user, date(2026, 3, 31), date(2026, 3, 1)
        ) == 0


class TestSpecialDays:
    def test_half_special_day_uses_the_factor(self, db, test_user, monkeypatch):
        """24.12. als halber Feiertag (#146/#394): das Tagessoll ist dort bereits
        halbiert, die Abwesenheits-Stunden müssen dem folgen."""
        from app.services import special_days_service

        monkeypatch.setattr(
            special_days_service, "get_special_day_config",
            lambda db, tid, year: {"dec24": "half_day", "dec31": "half_day",
                                   "dec24_counts_as_vacation": True,
                                   "dec31_counts_as_vacation": True},
        )
        monkeypatch.setattr(
            special_days_service, "special_day_target_factor",
            lambda d, cfg: Decimal("0.5") if d.month == 12 and d.day in (24, 31) else Decimal("1"),
        )
        xmas = date(2026, 12, 24)  # Donnerstag
        a = _absence(db, test_user, xmas, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user, effective_from=date(2026, 1, 1))

        changed = calculation_service.retarget_absence_hours(
            db, test_user, date(2026, 12, 1), date(2026, 12, 31)
        )
        assert changed == 1
        db.refresh(a)
        assert float(a.hours) == 2.0, "4 h Tagessoll × 0,5 Sondertagsfaktor"
