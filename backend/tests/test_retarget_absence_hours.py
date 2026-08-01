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
from app.models.system_setting import SystemSetting
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
    """Task 15: der Rückgabewert ist eine LISTE der geänderten Zeilen
    (``AbsenceRetarget``), nicht mehr die nackte Anzahl — der bisherige Zähler
    ist ``len(...)``. Aus dieser Liste baut der Router das Einzelprotokoll."""
    return calculation_service.retarget_absence_hours(
        db, user, WINDOW[0], WINDOW[1], dry_run=dry_run
    )


class TestAdjustsWhatItShould:
    def test_vacation_hours_follow_the_new_daily_target(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 1
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

        assert len(_run(db, test_user)) == 2
        db.refresh(sick); db.refresh(training)
        assert float(sick.hours) == 4.0
        assert float(training.hours) == 4.0

    def test_half_day_gets_half_the_target(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 4.0, half_day=True)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 1
        db.refresh(a)
        assert float(a.hours) == 2.0

    def test_paid_leave_and_other_are_adjusted(self, db, test_user):
        pl = _absence(db, test_user, MON, AbsenceType.PAID_LEAVE, 8.0)
        other = _absence(db, test_user, TUE, AbsenceType.OTHER, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 2
        db.refresh(pl); db.refresh(other)
        assert float(pl.hours) == 4.0 and float(other.hours) == 4.0


class TestLeavesAloneWhatItShould:
    def test_overtime_is_never_touched(self, db, test_user):
        """Freizeitausgleich trägt explizit beantragte Stunden, kein abgeleitetes
        Tagessoll — CLAUDE.md: Soll bleibt, Ist = 0."""
        a = _absence(db, test_user, MON, AbsenceType.OVERTIME, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_untracked_user_is_untouched(self, db, test_user):
        """track_hours=False (leitende Angestellte): dort zählt nur die
        Tageszählung, Stunden sind Rauschen."""
        test_user.track_hours = False
        db.commit()
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_weekend_is_skipped(self, db, test_user):
        a = _absence(db, test_user, SAT, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_public_holiday_is_skipped(self, db, test_user):
        db.add(PublicHoliday(
            date=WED, name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID,
        ))
        db.commit()
        a = _absence(db, test_user, WED, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_absence_before_first_work_day_untouched(self, db, test_user):
        test_user.first_work_day = date(2026, 3, 20)
        db.commit()
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_absence_after_last_work_day_untouched(self, db, test_user):
        test_user.last_work_day = date(2026, 3, 5)
        db.commit()
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_absence_outside_the_window_untouched(self, db, test_user):
        a = _absence(db, test_user, date(2026, 2, 9), AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user, effective_from=date(2026, 1, 1))

        assert len(_run(db, test_user)) == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_legacy_null_half_day_is_untouched(self, db, test_user):
        """C1: ``half_day IS NULL`` (Legacy-Zeile von vor #205) darf nicht
        angefasst werden. Fuer genau diese Zeilen zaehlen get_vacation_account
        und absence_days die TAGE stundenbasiert (hours / Tagessoll) — ein
        Retarget auf das volle Tagessoll wuerde den Tage-Verbrauch bewegen und
        die Information "war ein halber Tag" unwiederbringlich loeschen."""
        # 2 h auf einem 8-h-Tag: nach der Halbierung waere das volle Tagessoll
        # 4 h — ohne den Fix wuerde die Zeile also auf 4.0 umgeschrieben.
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 2.0, half_day=None)
        _halve_hours(db, test_user)  # 8 h -> 4 h Tagessoll

        assert len(_run(db, test_user)) == 0
        db.refresh(a)
        assert float(a.hours) == 2.0, "Legacy-Halbtag unveraendert"

    def test_legacy_null_half_day_keeps_the_day_count(self, db, test_user):
        """Die Invariante selbst: die Rueckrechnung darf den Urlaubs-TAGE-
        Verbrauch einer Legacy-Zeile nicht bewegen. Ohne den Fix schriebe sie
        das volle Tagessoll und used_days spraenge (0,5 -> 1,0)."""
        _absence(db, test_user, MON, AbsenceType.VACATION, 2.0, half_day=None)
        _halve_hours(db, test_user)
        db.expire_all()
        before = calculation_service.get_vacation_account(db, test_user, 2026)["used_days"]

        _run(db, test_user)
        db.expire_all()
        after = calculation_service.get_vacation_account(db, test_user, 2026)["used_days"]
        assert float(after) == float(before)

    def test_already_correct_hours_are_not_counted(self, db, test_user):
        """Idempotenz: ein zweiter Lauf darf nichts mehr melden."""
        _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 1
        assert len(_run(db, test_user)) == 0


class TestDryRun:
    def test_dry_run_counts_but_changes_nothing(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user, dry_run=True)) == 1
        db.refresh(a)
        assert float(a.hours) == 8.0, "dry_run darf nicht schreiben"

    def test_empty_window_returns_zero(self, db, test_user):
        assert calculation_service.retarget_absence_hours(
            db, test_user, date(2026, 3, 31), date(2026, 3, 1)
        ) == []


XMAS = date(2026, 12, 24)  # Donnerstag
DEC_WINDOW = (date(2026, 12, 1), date(2026, 12, 31))


def _half_special_day(db):
    """24./31.12.2026 als HALBEN Feiertag konfigurieren (#146) — echte Settings,
    kein monkeypatch: nur so laufen Schreiber (``retarget_absence_hours``) und
    Leser (``credit_day_weight`` / ``_day_soll_contribution``) durch dieselbe
    Quelle, und genau deren Zusammenspiel steht hier auf dem Prüfstand."""
    for prefix in ("special_day_dec24", "special_day_dec31"):
        db.add(SystemSetting(key=f"{prefix}_mode", value="half_day",
                             description=prefix, tenant_id=DEFAULT_TENANT_ID))
    db.commit()


class TestSpecialDays:
    def test_half_special_day_stores_the_UNFACTORED_daily_target(self, db, test_user):
        """Audit 2026-07-31 (Fund A): der Sondertagsfaktor gehört NICHT in den
        gespeicherten Wert.

        Alle anderen ``Absence.hours``-Schreiber (``absences.create_absence``,
        ``admin_change_requests.review_change_request``) buchen an einem
        Halbtags-Sondertag bewusst das VOLLE Tagessoll; der 0,5-Faktor lebt auf
        der Leseseite (``credit_day_weight`` fürs Ist, ``_day_soll_contribution``
        fürs Soll, ``half_special_day_weight`` für die Urlaubstage). Die
        Rückrechnung muss derselben Konvention folgen — sonst wird der Faktor
        zweimal angewandt (siehe die beiden Tests darunter).

        Früher erwartete dieser Test 2,0 (= 4 h × 0,5). Das war richtig, solange
        die Leseseite den Faktor NICHT anwandte; seit ``credit_day_weight``
        (Fund K) ist es doppelt gemoppelt."""
        _half_special_day(db)
        a = _absence(db, test_user, XMAS, AbsenceType.VACATION, 8.0)
        _halve_hours(db, test_user, effective_from=date(2026, 1, 1))

        changed = calculation_service.retarget_absence_hours(
            db, test_user, *DEC_WINDOW
        )
        assert len(changed) == 1
        db.refresh(a)
        assert float(a.hours) == 4.0, "volles Tagessoll (40→20 h/Woche), OHNE Sondertagsfaktor"

    def test_sick_on_half_special_day_stays_saldo_neutral(self, db, test_user):
        """Fund A, Kern: eine Krankmeldung am halben 24.12. ist saldo-neutral
        (§ 3 EntgFG) — Soll und Ist müssen sich decken, VOR und NACH einer
        Rückrechnung. Vorher: 2,00 Soll gegen 1,00 Ist = −1,00 h stilles Defizit
        an einem Tag, an dem sich fachlich nichts geändert hat."""
        _half_special_day(db)
        _absence(db, test_user, XMAS, AbsenceType.SICK, 8.0)

        before_soll = calculation_service.get_range_target(db, test_user, XMAS, XMAS)
        before_ist = calculation_service.get_range_actual(db, test_user, XMAS, XMAS)
        assert before_soll == before_ist == Decimal("4.00")

        _halve_hours(db, test_user, effective_from=date(2026, 1, 1))
        calculation_service.retarget_absence_hours(db, test_user, *DEC_WINDOW)
        db.expire_all()

        soll = calculation_service.get_range_target(db, test_user, XMAS, XMAS)
        ist = calculation_service.get_range_actual(db, test_user, XMAS, XMAS)
        assert soll == Decimal("2.00"), "20 h/Woche ⇒ 4 h Tagessoll × 0,5 Sondertag"
        assert ist == soll, f"Krankentag muss saldo-neutral bleiben (Soll {soll}, Ist {ist})"

    def test_retarget_is_idempotent_on_a_half_special_day(self, db, test_user):
        """Fund A, die eigentliche Klasse: ohne Vertragsänderung darf die
        Rückrechnung an einem Halbtags-Sondertag GAR NICHTS anfassen — und ein
        zweiter Lauf den Wert nicht erneut verschieben.

        Vorher wich der gespeicherte Wert dort IMMER vom neu berechneten ab (der
        Schreiber rechnete den Faktor hinein, der Buchungspfad nicht), also
        schlug die Gleichheitsprüfung bei JEDEM Lauf an — auch bei einer
        Änderung, die die Wochenstunden gar nicht anfasst."""
        _half_special_day(db)
        a = _absence(db, test_user, XMAS, AbsenceType.SICK, 8.0)

        first = calculation_service.retarget_absence_hours(db, test_user, *DEC_WINDOW)
        assert first == [], "unveränderter Vertrag ⇒ keine Zeile anzufassen"
        db.refresh(a)
        assert float(a.hours) == 8.0

        # Und auch nach einer echten Änderung konvergiert es nach EINEM Lauf.
        _halve_hours(db, test_user, effective_from=date(2026, 1, 1))
        assert len(calculation_service.retarget_absence_hours(db, test_user, *DEC_WINDOW)) == 1
        db.refresh(a)
        assert float(a.hours) == 4.0
        assert calculation_service.retarget_absence_hours(db, test_user, *DEC_WINDOW) == [], \
            "zweiter Lauf darf den Wert nicht erneut verschieben"
        db.refresh(a)
        assert float(a.hours) == 4.0

    def test_normal_day_unchanged(self, db, test_user):
        """Kontrolltest: an einem Tag OHNE Sondertagsregel ändert der Fix nichts."""
        _half_special_day(db)  # Config vorhanden, aber MON ist kein Sondertag
        a = _absence(db, test_user, MON, AbsenceType.SICK, 8.0)
        _halve_hours(db, test_user)

        assert len(_run(db, test_user)) == 1
        db.refresh(a)
        assert float(a.hours) == 4.0

    def test_free_special_day_follows_the_same_convention(self, db, test_user):
        """``free`` (Faktor 0) folgt derselben Konvention: gespeichert wird das
        volle Tagessoll, die 0 kommt von der Leseseite.

        Vorher lief der Tag ins ``target <= 0``-``continue`` und blieb auf den
        Stunden des ALTEN Vertrags stehen — genau die Drift, gegen die es die
        Rückrechnung gibt. Soll und Ist sind (unverändert) beide 0, die Zahlen
        im Beleg bewegen sich also nicht; nur der gespeicherte Wert wird ehrlich."""
        for prefix in ("special_day_dec24", "special_day_dec31"):
            db.add(SystemSetting(key=f"{prefix}_mode", value="free",
                                 description=prefix, tenant_id=DEFAULT_TENANT_ID))
        db.commit()
        a = _absence(db, test_user, XMAS, AbsenceType.SICK, 8.0)
        _halve_hours(db, test_user, effective_from=date(2026, 1, 1))

        assert len(calculation_service.retarget_absence_hours(db, test_user, *DEC_WINDOW)) == 1
        db.refresh(a)
        assert float(a.hours) == 4.0
        db.expire_all()
        assert calculation_service.get_range_target(db, test_user, XMAS, XMAS) == Decimal("0")
        assert calculation_service.get_range_actual(db, test_user, XMAS, XMAS) == Decimal("0")
