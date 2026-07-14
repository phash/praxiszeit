"""#377 Baustein 2b: zentrale Fix-Monats-Soll-Helper."""
from datetime import date, time
from decimal import Decimal
import pytest
from app.models import User, UserRole, Absence, AbsenceType, PublicHoliday, TimeEntry, YearCarryover
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID


def _mk(db, **kw):
    base = dict(username="fx", email="fx@t.l", password_hash="x", first_name="F",
                last_name="X", role=UserRole.EMPLOYEE, weekly_hours=Decimal("10"),
                work_days_per_week=2, track_hours=True, is_active=True,
                use_daily_schedule=True, use_fixed_monthly_target=True,
                agreed_monthly_hours=Decimal("40"),
                hours_monday=Decimal("3"), hours_wednesday=Decimal("3"),
                tenant_id=DEFAULT_TENANT_ID)
    base.update(kw)
    u = User(**base); db.add(u); db.commit(); db.refresh(u)
    return u


def test_fixed_target_is_flat_across_months(db, default_tenant):
    u = _mk(db)
    # März 2025 (5 Montage) vs Feb 2025 (4 Montage) → beide 40h fix.
    assert cs.fixed_monthly_target(u, 2025, 3) == Decimal("40.00")
    assert cs.fixed_monthly_target(u, 2025, 2) == Decimal("40.00")


def test_fixed_target_prorata_on_entry(db, default_tenant):
    u = _mk(db, first_work_day=date(2025, 3, 16))  # 16 von 31 Tagen im Fenster
    assert cs.fixed_monthly_target(u, 2025, 3) == (Decimal("40") * 16 / 31).quantize(Decimal("0.01"))


def test_fixed_target_zero_when_flag_off(db, default_tenant):
    u = _mk(db, use_fixed_monthly_target=False)
    assert cs.fixed_monthly_target(u, 2025, 3) == Decimal("0")


def test_credit_holiday_on_planned_day(db, default_tenant):
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 3), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Montag
    db.commit()
    # geplante Mo-Stunden = 3 → Gutschrift 3
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("3.00")


def test_credit_holiday_on_unplanned_day_is_zero(db, default_tenant):
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 4), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Dienstag, ungeplant
    db.commit()
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("0.00")


def test_credit_vacation_but_not_sick(db, default_tenant):
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.VACATION, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 12),
                   type=AbsenceType.SICK, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.commit()
    # NUR VACATION zählt hier (SICK läuft über credited_absences → keine Doppelgutschrift)
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("3.00")


def test_unpaid_other_reduces_soll(db, default_tenant):
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.commit()
    assert cs.fixed_month_unpaid_reduction(db, u, 2025, 3) == Decimal("3.00")


def test_unpaid_reduction_skips_holiday_day_no_double_count(db, default_tenant):
    """Finding 2 (Whole-Branch-Review, cross-set double-count guard): ein Tag,
    der GLEICHZEITIG Feiertag ist UND eine ganztägige OTHER-Abwesenheit trägt,
    darf das Konto nur EINMAL um die geplanten Stunden bewegen (Gutschrift über
    fixed_month_credit), NICHT zusätzlich über fixed_month_unpaid_reduction
    mindern (sonst +2× planned statt +1×) — der Feiertag ist bereits über die
    Credit-Seite abgedeckt."""
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 3), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Montag, geplant 3h
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 3),
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))
    db.commit()

    # Unpaid-Pfad muss den Feiertags-Tag ÜBERSPRINGEN — der wird schon über die
    # Credit-Seite gutgeschrieben.
    assert cs.fixed_month_unpaid_reduction(db, u, 2025, 3) == Decimal("0.00")
    # Credit-Seite unverändert: Feiertag auf geplantem Mo → +3.
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("3.00")

    # Monats-Soll bleibt fix (nicht gemindert), Ist trägt genau EINE Gutschrift.
    assert cs.get_monthly_target(db, u, 2025, 3) == Decimal("40.00")
    assert cs.get_monthly_actual(db, u, 2025, 3) == Decimal("3.00")

    # Ein zweiter MA mit NUR dem (tenant-weiten) Feiertag, aber OHNE die
    # zusätzliche OTHER-Absence an demselben Tag, muss EXAKT dasselbe Soll/Ist
    # zeigen — die OTHER-Absence auf einem Feiertag darf das Konto NICHT
    # zusätzlich bewegen (das wäre der Doppelzähl-Fehler: +2× statt +1×
    # planned). Bewusst kein "ganz ohne Feiertag"-Baseline, da PublicHoliday
    # tenant-weit gilt und beide MA im selben Tenant sitzen.
    holiday_only = _mk(db, username="fx-holiday-only", email="fxho@t.l")
    assert cs.get_monthly_target(db, holiday_only, 2025, 3) == cs.get_monthly_target(db, u, 2025, 3)
    assert cs.get_monthly_actual(db, holiday_only, 2025, 3) == cs.get_monthly_actual(db, u, 2025, 3)


def test_unpaid_reduction_still_applies_on_non_holiday(db, default_tenant):
    """Regressions-Anker zu Finding 2: der neue Holiday-Skip darf die normale
    (Nicht-Feiertags-)Reduktion nicht kaputt machen — bereits von
    test_unpaid_other_reduces_soll abgedeckt, hier zusätzlich explizit
    gegengeprüft, dass KEIN Feiertag am selben Tag liegt."""
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))  # Mi geplant, kein Feiertag
    db.commit()
    assert cs.fixed_month_unpaid_reduction(db, u, 2025, 3) == Decimal("3.00")


def test_monthly_target_fixed_mode(db, default_tenant):
    u = _mk(db)
    assert cs.get_monthly_target(db, u, 2025, 3) == Decimal("40.00")  # nicht Σ Tagesstunden
    assert cs.get_monthly_target(db, u, 2025, 2) == Decimal("40.00")


def test_monthly_target_unpaid_reduces(db, default_tenant):
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))
    db.commit()
    assert cs.get_monthly_target(db, u, 2025, 3) == Decimal("37.00")  # 40 − 3 unbezahlt


def test_range_target_non_mode_byte_identical(db, default_tenant):
    u = _mk(db, use_fixed_monthly_target=False, weekly_hours=Decimal("40"), work_days_per_week=5,
            use_daily_schedule=False, agreed_monthly_hours=None)
    # Referenzwert: Σ 8h über die Werktage im März 2025 (21 Werktage) = 168
    assert cs.get_monthly_target(db, u, 2025, 3) == Decimal("168.00")


def test_range_target_unpaid_absence_not_smeared_across_weeks(db, default_tenant):
    """Review-Medium: eine unbezahlte Abwesenheit an EINEM Tag darf nur die Woche
    mindern, die diesen Tag enthält — nicht gleichmäßig über alle Wochen des
    Monats verteilt werden ("smearing"). Absence: Mo 2025-03-03 (geplant, 3h).
    Testwoche 10.-16.03. enthält den 03.03. NICHT → darf keine Reduktion sehen."""
    u_with = _mk(db)
    db.add(Absence(user_id=u_with.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 3),
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))  # Mo geplant
    db.commit()
    u_without = _mk(db, username="fx2", email="fx2@t.l")

    week_with = cs.get_range_target(db, u_with, date(2025, 3, 10), date(2025, 3, 16))
    week_without = cs.get_range_target(db, u_without, date(2025, 3, 10), date(2025, 3, 16))
    assert week_with == week_without

    # Whole-month Soll still counts the unpaid reduction (37 = 40 − 3).
    assert cs.get_monthly_target(db, u_with, 2025, 3) == Decimal("37.00")


def test_credit_mixed_half_day_vacation_and_paid_leave_same_date(db, default_tenant):
    """Misch-Tag: ½ VACATION + ½ PAID_LEAVE am selben geplanten Mi (3h Soll)
    müssen zusammen den VOLLEN Tag (3.00) gutschreiben, nicht nur die 2. Hälfte
    (1.50) — {date: a}-Dict würde den 1. Eintrag beim Überschreiben verlieren."""
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.VACATION, hours=Decimal("1.5"), half_day=True))  # Mi geplant
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.PAID_LEAVE, hours=Decimal("1.5"), half_day=True))  # gleicher Tag
    db.commit()
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("3.00")


def test_monthly_actual_credits_holiday(db, default_tenant):
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 3), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Mo
    db.commit()
    # kein TimeEntry → Ist = 0 + Gutschrift 3 (geplante Mo-Stunden)
    assert cs.get_monthly_actual(db, u, 2025, 3) == Decimal("3.00")


def test_range_actual_credit_not_smeared_across_weeks(db, default_tenant):
    """Analog zu Task 3 (get_range_target): eine Feiertags-Gutschrift in Woche A
    darf nicht in die Ist-Abfrage einer ANDEREN Woche desselben Monats
    durchsickern — from_date muss den Monats-Credit range-genau begrenzen."""
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 3), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Mo, Woche A
    db.commit()

    week_a = cs.get_range_actual(db, u, date(2025, 3, 3), date(2025, 3, 9))
    week_b = cs.get_range_actual(db, u, date(2025, 3, 10), date(2025, 3, 16))
    assert week_a == Decimal("3.00")
    assert week_b == Decimal("0.00")

    # Ganzer Monat trägt weiterhin die volle Gutschrift.
    assert cs.get_monthly_actual(db, u, 2025, 3) == Decimal("3.00")


def test_overtime_account_fixed_mode(db, default_tenant):
    """#377 Baustein 2b: get_overtime_account muss im Fix-Modus das FESTE
    Monats-Soll (40h) nutzen, nicht die schwankende Per-Tag-Summe (2 Tage/Woche
    à 3h). 30h real erfasst → Konto = 30 − 40 = −10.00."""
    u = _mk(db)  # agreed 40/Monat
    for d in (5, 12, 19):  # 3× 10h netto (8:00-19:00 minus 60min Pause) = 30h
        db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, d),
                         start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()
    assert cs.get_overtime_account(db, u, 2025, 3) == Decimal("-10.00")


def test_overtime_account_non_mode_byte_identical(db, default_tenant):
    """Nicht-Modus-MA müssen weiterhin die Per-Tag-Summe nutzen (unverändert)."""
    u = _mk(db, use_fixed_monthly_target=False, weekly_hours=Decimal("40"), work_days_per_week=5,
            use_daily_schedule=False, agreed_monthly_hours=None)
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                     start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()
    # Soll = Σ 8h über 21 Werktage im März 2025 = 168; Ist = 10h → Konto = 10 − 168
    assert cs.get_overtime_account(db, u, 2025, 3) == Decimal("10.00") - Decimal("168.00")


def test_ytd_summary_fixed_mode(db, default_tenant):
    """#377 Baustein 2b: get_ytd_summary muss im Fix-Modus das FESTE Monats-Soll
    (40h) je Monat summieren, nicht die Per-Tag-Summe. Jahr 2026 = aktuelles
    Jahr (Testlauf), damit cutoff_date (#313) tatsächlich als YTD-Grenze
    greift (Vorjahre laufen sonst immer bis 31.12.). Ohne Einträge: YTD-Soll
    bis 31.03. = 3×40 = 120 (Jan+Feb+Mär), Ist = Gutschriften (hier 0)."""
    u = _mk(db)
    r = cs.get_ytd_summary(db, u, 2026, cutoff_date=date(2026, 3, 31))
    assert r["target_hours"] == 120.00


def test_ytd_summary_non_mode_byte_identical(db, default_tenant):
    """Nicht-Modus-MA müssen weiterhin die Per-Tag-Summe/Inline-Schleife nutzen
    (unverändert) — Regressionsanker für den Modus-Branch."""
    u = _mk(db, use_fixed_monthly_target=False, weekly_hours=Decimal("40"), work_days_per_week=5,
            use_daily_schedule=False, agreed_monthly_hours=None)
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 5),
                     start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()
    r = cs.get_ytd_summary(db, u, 2026, cutoff_date=date(2026, 3, 31))
    # Soll = Σ 8h über die Werktage Jan-Mär 2026 bis 31.03.; Ist = 10h.
    expected_target = (cs.get_range_target(db, u, date(2026, 1, 1), date(2026, 3, 31)))
    assert Decimal(str(r["target_hours"])) == expected_target
    assert Decimal(str(r["actual_hours"])) == Decimal("10.00")


# --- Task 7: Parallelpfad-Konsistenz + Byte-Identität + cutoff/carryover ---
#
# Jahr 2026 statt der im Task-Brief illustrierten 2025: get_ytd_summary
# behandelt nur das "laufende" Jahr (year == today.year) cutoff-sensitiv
# (sonst end := 31.12., der cutoff wird ignoriert — siehe #313-Kommentar im
# Service). Da der reale Testlauf-"heute" inzwischen in 2026 liegt (wie schon
# test_ytd_summary_fixed_mode/_non_mode_byte_identical oben dokumentieren),
# muss 2026 verwendet werden, damit cutoff_date tatsächlich als YTD-Grenze
# greift — sonst würde die YTD-Summe stillschweigend über alle 12 Monate
# laufen und nicht mit dem auf März begrenzten Konto übereinstimmen.

def test_parallel_paths_consistent(db, default_tenant):
    """#377 Baustein 2b (Haupttest, Task 7): get_overtime_account() (Task 5)
    und die davon UNABHÄNGIG aufgebaute Σ(get_monthly_actual − get_monthly_
    target)-Rekonstruktion dürfen für einen Modus-MA mit gemischtem Jan-Mär
    (reale TimeEntries, 1 Feiertag, 1 VACATION, 1 OTHER — je auf einem
    geplanten Mo/Mi) NIE auseinanderlaufen. Genau diese Klasse von
    Parallelpfad-Divergenz traf Release 1.14.3.

    Handberechnung (agreed=40/Monat fix, Mo+Mi geplant à 3h):
      Jan: 2× TimeEntry (Mo 05.01./19.01., je 10h netto) → Ist 20.00,
           kein Feiertag/Abwesenheit → Soll 40.00 (flach)          Δ -20.00
      Feb: 1 Feiertag auf geplantem Mo (02.02.), kein TimeEntry →
           Ist = Gutschrift der geplanten Mo-Stunden = 3.00,
           Soll unverändert 40.00 (Feiertag mindert NICHT das Soll,
           er wird nur dem Ist gutgeschrieben)                     Δ -37.00
      Mär: VACATION auf geplantem Mi (04.03., 3h, ganztägig) →
           Ist-Gutschrift 3.00; OTHER (unbezahlt) auf geplantem Mo
           (02.03., 3h, ganztägig) mindert das Soll auf 37.00      Δ -34.00
      Σ Δ = -20.00 -37.00 -34.00 = -91.00
    """
    u = _mk(db)  # agreed=40/Monat, Mo+Mi geplant à 3h, Fenster offen
    for d in (5, 19):  # Jan: 2 reale Mo-Einträge, je 10h netto (8-19h, 60min Pause)
        db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 1, d),
                         start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.add(PublicHoliday(date=date(2026, 2, 2), name="X", year=2026, tenant_id=DEFAULT_TENANT_ID))  # Mo
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 4),  # Mi
                   type=AbsenceType.VACATION, hours=Decimal("3"), half_day=False))
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 2),  # Mo
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))
    db.commit()

    expected_target = {1: Decimal("40.00"), 2: Decimal("40.00"), 3: Decimal("37.00")}
    expected_actual = {1: Decimal("20.00"), 2: Decimal("3.00"), 3: Decimal("3.00")}
    for m in (1, 2, 3):
        assert cs.get_monthly_target(db, u, 2026, m) == expected_target[m]
        assert cs.get_monthly_actual(db, u, 2026, m) == expected_actual[m]

    manual = sum((expected_actual[m] - expected_target[m] for m in (1, 2, 3)), Decimal("0"))
    assert manual == Decimal("-91.00")

    acc = cs.get_overtime_account(db, u, 2026, 3)
    assert acc == manual.quantize(Decimal("0.01"))

    ytd = cs.get_ytd_summary(db, u, 2026, cutoff_date=date(2026, 3, 31))
    assert Decimal(str(ytd["overtime"])) == acc  # Carryover 0 in diesem Test


def test_byte_identity_non_mode_all_four_surfaces(db, default_tenant):
    """Task 7 Nr. 2: ein NICHT-Modus-MA muss über ALLE VIER Soll/Ist-
    Oberflächen (get_monthly_target, get_monthly_actual, get_overtime_account,
    get_ytd_summary) unverändert die alte (modus-freie) Per-Tag-Rechnung
    liefern — Regressionsanker, dass die #377-Modus-Zweige den Nicht-Modus-
    Pfad nirgends berühren.

    Referenz (handgezählt via calendar.monthrange, 8h/Werktag = 40h/5 Tage):
      Werktage 2026: Jan=22, Feb=20, Mär=22 → Jan-Mär gesamt 64.
      TimeEntry am 04.03.2026 (Mi), 8-19h minus 60min Pause = 10h netto.
    """
    u = _mk(db, use_fixed_monthly_target=False, weekly_hours=Decimal("40"), work_days_per_week=5,
            use_daily_schedule=False, agreed_monthly_hours=None)
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 4),
                     start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()

    assert cs.get_monthly_target(db, u, 2026, 3) == Decimal("176.00")  # 22 Werktage × 8h
    assert cs.get_monthly_actual(db, u, 2026, 3) == Decimal("10.00")
    assert cs.get_overtime_account(db, u, 2026, 3) == Decimal("10.00") - Decimal("176.00")

    ytd = cs.get_ytd_summary(db, u, 2026, cutoff_date=date(2026, 3, 31))
    assert Decimal(str(ytd["target_hours"])) == Decimal("512.00")  # 64 Werktage × 8h (Jan+Feb+Mär)
    assert Decimal(str(ytd["actual_hours"])) == Decimal("10.00")
    assert Decimal(str(ytd["overtime"])) == Decimal("10.00") - Decimal("512.00")


def test_overtime_account_cutoff_uses_prorata_target(db, default_tenant):
    """#377 Baustein 2b / Task 5 (deferred minor, Task 7 Nr. 3): get_overtime_
    account mit einem MITTEN-im-Monat-cutoff_date (#313-Dashboard-Pfad) MUSS
    für einen Modus-MA das ANTEILIGE (pro-rata) Monats-Soll nutzen, nicht das
    volle Fix-Soll — sonst zeigt der laufende Monat ein Phantom-Defizit in
    Höhe der noch nicht abgelaufenen Resttage.

    Ein TimeEntry NACH dem Cutoff dient nur als Konto-Startpunkt
    (get_overtime_account leitet start_year/start_month vom ersten TimeEntry
    des Users ab) und wird durch den Cutoff selbst aus dem Ist ausgeschlossen
    → Ist=0 im betrachteten Fenster ("no entries"-Fall aus dem Task-Brief).

    Cutoff = 15.03.2026 (15 von 31 Kalendertagen, Beschäftigungsfenster
    durchgehend offen, keine unbezahlte Abwesenheit) → erwartetes Pro-rata-
    Soll = 40 × 15/31 = 19.35, unabhängig von get_monthly_target per
    Dezimal-Arithmetik handberechnet (NICHT durch einen zweiten SUT-Aufruf)."""
    u = _mk(db)  # agreed=40
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 20),  # nach dem Cutoff
                     start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()

    expected_target = (Decimal("40") * 15 / 31).quantize(Decimal("0.01"))
    assert expected_target == Decimal("19.35")

    acc = cs.get_overtime_account(db, u, 2026, 3, cutoff_date=date(2026, 3, 15))
    assert acc == -expected_target


def test_ytd_summary_fixed_mode_folds_in_carryover(db, default_tenant):
    """#377 Baustein 2b / Task 6 (deferred minor, Task 7 Nr. 4): get_ytd_
    summary muss im Fix-Modus einen vorhandenen YearCarryover GENAUSO in
    ``overtime`` einfalten wie der Nicht-Modus-Pfad
    (``overtime = total_actual − total_target + carryover_hours``).

    Handberechnung (agreed=40/Monat fix, cutoff 31.03.2026 → Jan+Feb+Mär):
      Jan: Soll 40.00, Ist 0.00 (keine Einträge)
      Feb: Soll 40.00, Ist 0.00 (keine Einträge)
      Mär: Soll 40.00, Ist 10.00 (1× TimeEntry, 8-19h minus 60min Pause)
      Σ Soll = 120.00, Σ Ist = 10.00, Carryover = 5.00
      overtime = 10.00 − 120.00 + 5.00 = −105.00
    """
    u = _mk(db)  # agreed=40
    db.add(YearCarryover(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                         overtime_hours=Decimal("5"), vacation_days=Decimal("0")))
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 4),
                     start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()

    ytd = cs.get_ytd_summary(db, u, 2026, cutoff_date=date(2026, 3, 31))
    assert Decimal(str(ytd["target_hours"])) == Decimal("120.00")
    assert Decimal(str(ytd["actual_hours"])) == Decimal("10.00")
    assert Decimal(str(ytd["carryover_hours"])) == Decimal("5.00")

    expected_overtime = Decimal("10.00") - Decimal("120.00") + Decimal("5.00")
    assert expected_overtime == Decimal("-105.00")
    assert Decimal(str(ytd["overtime"])) == expected_overtime


# --- Task 8: get_overtime_history_detailed / settlement_aging-Kohärenz ------
#
# get_overtime_history_detailed baute Soll/Ist bislang PER-TAG inline nach (wie
# get_overtime_account vor Task 5) — für einen Modus-MA divergierte das vom
# (jetzt modus-korrekten) get_monthly_target/get_monthly_actual und verletzte
# damit die eigene gepinnte Invariante (Docstring). settlement_aging (milog_
# service) konsumiert genau diese Monats-Deltas (actual − target) für das
# 12-Monats-FIFO-Aging — eine Divergenz dort fabriziert Phantom-Defizite aus
# gutgeschriebenen Feiertagen/Urlaub.

def test_history_detailed_matches_wrappers_fixed_mode(db, default_tenant):
    """Gepinnte Invariante (MonthlyOvertime-Docstring) für einen Modus-MA über
    einen Jan-Mär-Mix (reale TimeEntries, 1 Feiertag, 1 VACATION, 1 OTHER —
    dieselben Zahlen wie test_parallel_paths_consistent, Task 7)."""
    u = _mk(db)  # agreed=40/Monat, Mo+Mi geplant à 3h, Fenster offen
    for d in (5, 19):  # Jan: 2 reale Mo-Einträge, je 10h netto (8-19h, 60min Pause)
        db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 1, d),
                         start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.add(PublicHoliday(date=date(2026, 2, 2), name="X", year=2026, tenant_id=DEFAULT_TENANT_ID))  # Mo
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 4),  # Mi
                   type=AbsenceType.VACATION, hours=Decimal("3"), half_day=False))
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 2),  # Mo
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))
    db.commit()

    detailed = cs.get_overtime_history_detailed(db, u, 2026, 3)
    for m in (1, 2, 3):
        assert detailed[(2026, m)].target == cs.get_monthly_target(db, u, 2026, m)
        assert detailed[(2026, m)].actual == cs.get_monthly_actual(db, u, 2026, m)
    assert detailed[(2026, 3)].cumulative == cs.get_overtime_account(db, u, 2026, 3)


def test_history_detailed_non_mode_byte_identical(db, default_tenant):
    """Regressionsanker: ein NICHT-Modus-MA muss get_overtime_history_detailed
    weiterhin unverändert (Per-Tag-Inline) liefern — der neue Modus-Branch
    darf den Nicht-Modus-Pfad nirgends berühren."""
    u = _mk(db, use_fixed_monthly_target=False, weekly_hours=Decimal("40"), work_days_per_week=5,
            use_daily_schedule=False, agreed_monthly_hours=None)
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 4),
                     start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()

    detailed = cs.get_overtime_history_detailed(db, u, 2026, 3)
    assert detailed[(2026, 3)].target == Decimal("176.00")  # 22 Werktage × 8h
    assert detailed[(2026, 3)].actual == Decimal("10.00")
    assert detailed[(2026, 3)].cumulative == cs.get_overtime_account(db, u, 2026, 3)


def test_settlement_aging_no_phantom_deficit_fixed_mode(db, default_tenant):
    """#377 Baustein 2b (Task 8): ein Modus-MA mit EINEM Feiertag auf einem
    geplanten Tag in einem sonst leeren ("Nur-Feiertag") Monat darf im
    12-Monats-FIFO-Aging (settlement_aging) KEIN Defizit erzeugen — der
    Feiertag ist gutgeschrieben (fixed_month_credit), also target == actual
    für diesen Monat (agreed extra klein gewählt = genau die Feiertags-
    Gutschrift, damit das ohne weitere Arbeitstage exakt aufgeht).

    ``first_work_day=2025-03-01`` grenzt das Beschäftigungsfenster auf genau
    den betrachteten Monat ein, damit Jan/Feb (außerhalb des Fensters, Soll
    UND Ist beide 0) keine unabhängigen Hintergrund-Deltas beisteuern — der
    Test isoliert so exakt den Feiertags-Effekt. ``YearCarryover(0)`` dient
    NUR als Anker, damit get_overtime_history_detailed einen Startpunkt hat
    (ohne TimeEntry/Carryover bricht die Funktion mit einem leeren Dict ab)."""
    from app.services import milog_service
    u = _mk(db, agreed_monthly_hours=Decimal("3"), milog_working_time_account=True,
            first_work_day=date(2025, 3, 1))
    db.add(PublicHoliday(date=date(2025, 3, 3), name="X", year=2025,
                         tenant_id=DEFAULT_TENANT_ID))  # Montag, geplant (3h)
    db.add(YearCarryover(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, year=2025,
                         overtime_hours=Decimal("0"), vacation_days=Decimal("0")))
    db.commit()

    # Pinned invariant zuerst: kein Phantom-Delta im Detail-Pass.
    detailed = cs.get_overtime_history_detailed(db, u, 2025, 3)
    assert detailed[(2025, 1)].target == Decimal("0.00")  # außerhalb des Fensters
    assert detailed[(2025, 1)].actual == Decimal("0.00")
    assert detailed[(2025, 2)].target == Decimal("0.00")
    assert detailed[(2025, 2)].actual == Decimal("0.00")
    assert detailed[(2025, 3)].target == Decimal("3.00")
    assert detailed[(2025, 3)].actual == Decimal("3.00")

    # Das oben gepinnte (vollmonatige) `detailed` übergeben — exakt wie die Prod-
    # Caller (dashboard.py / admin_users.py) es vor-berechnet durchreichen. So
    # prüft der Test die Fixed-Mode-Kohärenz (target==actual → delta 0 → keine
    # Einlage → None), nicht den #404-Direkt-self-fetch-Pfad (der wendet den #313-
    # Stichtag an und hat seinen eigenen Test in test_milog.py; im laufenden Monat
    # ergäbe der Stichtag ein winziges, nicht-überfälliges, warnungs-freies Delta).
    aging = milog_service.settlement_aging(db, u, date(2025, 3, 31), detailed=detailed)
    # Kein Monats-Delta ≠ 0 in der Historie → keine Einlage → kein offener
    # Posten → None (KEIN Phantom-Defizit / keine Überfälligkeits-Warnung).
    assert aging is None


# --- Task 9: MILOG_MONTHLY_EXCEEDED weiche Plausibilitäts-Warnung ----------

def test_monthly_exceeded_warning(db, default_tenant):
    """agreed=40h, 45h real erfasst im März 2025 → Warnung mit month_actual >
    agreed (5× 9h-Einträge, 8-18h minus 60min Pause = 45.00h netto)."""
    from app.services import milog_service
    u = _mk(db, agreed_monthly_hours=Decimal("40"))
    for d in (3, 4, 5, 6, 7):
        db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, d),
                         start_time=time(8, 0), end_time=time(18, 0), break_minutes=60))
    db.commit()
    chk = milog_service.monthly_exceeded_check(db, u, 2025, 3)
    assert chk is not None and chk["month_actual"] > chk["agreed"]
    assert chk["month_actual"] == 45.00
    assert chk["agreed"] == 40.00
    text = milog_service.monthly_exceeded_warning_text(chk)
    assert "MILOG_MONTHLY_EXCEEDED" in text
    assert "sofern zur Mindestlohnhöhe vergütet" in text


def test_monthly_exceeded_none_when_ist_not_over_agreed(db, default_tenant):
    """9h erfasst ≤ 40h agreed → keine Warnung."""
    from app.services import milog_service
    u = _mk(db, agreed_monthly_hours=Decimal("40"))
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 3),
                     start_time=time(8, 0), end_time=time(18, 0), break_minutes=60))
    db.commit()
    assert milog_service.monthly_exceeded_check(db, u, 2025, 3) is None


def test_monthly_exceeded_none_when_mode_off(db, default_tenant):
    """Fix-Modus aus → None, auch bei viel erfasster Zeit."""
    from app.services import milog_service
    u = _mk(db, use_fixed_monthly_target=False, agreed_monthly_hours=None,
            weekly_hours=Decimal("40"), work_days_per_week=5, use_daily_schedule=False)
    for d in (3, 4, 5, 6, 7):
        db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, d),
                         start_time=time(8, 0), end_time=time(18, 0), break_minutes=60))
    db.commit()
    assert milog_service.monthly_exceeded_check(db, u, 2025, 3) is None
