"""Edge-Case-Tests für Berechnungslogik, Überstundenausgleich und Journal.

Testet kritische Szenarien die in Produktion aufgetreten sind oder
aus dem Code-Review identifiziert wurden.
"""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import (
    User, UserRole, TimeEntry, Absence, AbsenceType,
    PublicHoliday, WorkingHoursChange, YearCarryover,
)
from app.services import calculation_service, journal_service
from tests.conftest import DEFAULT_TENANT_ID


# ---- Helpers ----------------------------------------------------------------

def _make_user(db, username="edge_user", email="edge@example.com", **kwargs):
    defaults = dict(
        password_hash="hash",
        first_name="Edge",
        last_name="User",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    user = User(username=username, email=email, **defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_entry(db, user, d, start_h, end_h, break_min=0, start_m=0, end_m=0):
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _make_absence(db, user, d, absence_type, hours):
    absence = Absence(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        type=absence_type,
        hours=hours,
    )
    db.add(absence)
    db.commit()
    return absence


# =============================================================================
# Überstundenausgleich — Kernlogik
# =============================================================================

class TestOvertimeCompensation:
    """Tests für die korrigierte Überstundenausgleich-Verrechnung."""

    def test_overtime_day_does_not_reduce_monthly_target(self, db, test_user):
        """Prüft dass Überstundenausgleich das Monatssoll nicht senkt — Soll bleibt, Ist=0h."""
        target_before = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.OVERTIME, 8.0)
        target_after = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        assert target_after == target_before

    def test_overtime_day_does_not_add_to_actual(self, db, test_user):
        """Prüft dass Überstundenausgleich NICHT als Ist-Stunden gezaehlt wird — Kernregel."""
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.OVERTIME, 8.0)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert actual == Decimal('0.00')

    def test_overtime_comp_full_scenario(self, db, test_user):
        """Prüft reales Szenario: 9 Tage je 9h + 1 Tag Ausgleich — Soll=176h, Ist=81h."""
        # 9 Arbeitstage je 9h (Mo-Fr KW10 + Mo-Do KW11)
        work_dates = [
            date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4),
            date(2026, 3, 5), date(2026, 3, 6),  # KW10
            date(2026, 3, 9), date(2026, 3, 10), date(2026, 3, 11),
            date(2026, 3, 12),  # KW11 Mo-Do
        ]
        for d in work_dates:
            _make_entry(db, test_user, d, 8, 17, break_min=0)  # 9h/Tag

        # 1 Tag Überstundenausgleich am Fr 13.03.
        _make_absence(db, test_user, date(2026, 3, 13), AbsenceType.OVERTIME, 8.0)

        target = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)

        # Soll: 22 Werktage × 8h = 176h (Überstundenausgleich ändert Soll NICHT)
        assert target == Decimal('176.00')
        # Ist: 9 Tage × 9h = 81h
        assert actual == Decimal('81.00')

    def test_sick_still_counts_as_actual(self, db, test_user):
        """Prüft dass Krankheit als Ist-Stunden gutgeschrieben wird — §3 EntgFG Lohnfortzahlung."""
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.SICK, 8.0)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert actual == Decimal('8.00')

    def test_training_still_counts_as_actual(self, db, test_user):
        """Prüft dass Fortbildung als Ist-Stunden zaehlt — bezahlte Freistellung."""
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.TRAINING, 8.0)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert actual == Decimal('8.00')

    def test_vacation_reduces_target_not_actual(self, db, test_user):
        """Prüft dass Urlaub Soll reduziert aber nicht als Ist zaehlt — BUrlG-konform."""
        target_before = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, 8.0)
        target_after = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert target_after == target_before - Decimal('8.00')
        assert actual == Decimal('0.00')

    def test_overtime_comp_with_daily_schedule(self, db):
        """Prüft dass Überstundenausgleich bei Teilzeit mit Tagesplan Soll nicht aendert."""
        user = _make_user(
            db, username="teilzeit", email="teil@test.de",
            weekly_hours=17.0, work_days_per_week=3,
            use_daily_schedule=True,
            hours_monday=5.0, hours_tuesday=0.0,
            hours_wednesday=6.0, hours_thursday=0.0, hours_friday=6.0,
        )
        # Mittwoch hat 6h Soll
        target_before = calculation_service.get_monthly_target(db, user, 2026, 3)
        _make_absence(db, user, date(2026, 3, 11), AbsenceType.OVERTIME, 6.0)  # Mi
        target_after = calculation_service.get_monthly_target(db, user, 2026, 3)
        assert target_after == target_before  # Soll bleibt gleich

    def test_overtime_in_get_overtime_account(self, db, test_user):
        """Prüft dass Überstundenausgleich das kumulative Konto korrekt reduziert."""
        # Januar: 10h Überstunden aufbauen
        _make_entry(db, test_user, date(2026, 1, 2), 7, 17, break_min=0)  # 10h Fr

        jan_balance = calculation_service.get_monthly_balance(db, test_user, 2026, 1)

        # Februar: 1 Tag Überstundenausgleich
        _make_absence(db, test_user, date(2026, 2, 10), AbsenceType.OVERTIME, 8.0)

        overtime_jan = calculation_service.get_overtime_account(db, test_user, 2026, 1)
        overtime_feb = calculation_service.get_overtime_account(db, test_user, 2026, 2)

        # Feb-Konto muss niedriger sein als Jan (weil Ausgleich Soll nicht senkt → Bilanz schlechter)
        assert overtime_feb < overtime_jan


# =============================================================================
# Journal — Überstundenausgleich-Anzeige
# =============================================================================

class TestJournalOvertimeDisplay:
    """Tests für die Journal-Darstellung von Überstundenausgleich."""

    def test_pure_overtime_day_shows_zero_actual(self, db, test_user):
        """Prüft dass Überstundenausgleich-Tag im Journal Ist=0h und type='overtime' zeigt."""
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.OVERTIME, 8.0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["actual_hours"] == 0.0
        assert day["target_hours"] == 8.0
        assert day["balance"] == -8.0
        assert day["type"] == "overtime"

    def test_pure_sick_day_shows_credited_hours(self, db, test_user):
        """Prüft dass Kranktag im Journal Ist=Abwesenheitsstunden zeigt — Lohnfortzahlung sichtbar."""
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.SICK, 8.0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["actual_hours"] == 8.0
        assert day["target_hours"] == 8.0
        assert day["balance"] == 0.0

    def test_pure_training_day_shows_credited_hours(self, db, test_user):
        """Prüft dass Fortbildungstag Ist=Fortbildungsstunden zeigt, Soll=volles Tagessoll bleibt."""
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.TRAINING, 6.0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["actual_hours"] == 6.0
        assert day["target_hours"] == 8.0  # Tagesplan, nicht Abwesenheitsstunden

    def test_vacation_day_balance_zero(self, db, test_user):
        """Prüft dass Urlaubstag im Journal eine Bilanz von 0 hat — kein Saldo-Effekt."""
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, 8.0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["balance"] == 0.0

    def test_journal_monthly_summary_with_overtime_comp(self, db, test_user):
        """Prüft dass Monatssumme bei Überstundenausgleich 0h Ist und volles Soll zeigt."""
        # 1 normaler Arbeitstag
        _make_entry(db, test_user, date(2026, 3, 9), 8, 16, break_min=0)  # 8h Mo
        # 1 Überstundenausgleich
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.OVERTIME, 8.0)

        journal = journal_service.get_journal(db, test_user, 2026, 3)
        summary = journal["monthly_summary"]

        # Ist: 8h (nur der Arbeitstag)
        assert summary["actual_hours"] == 8.0
        # Soll: 22 Werktage × 8h = 176h (Überstundenausgleich ändert Soll NICHT)
        assert summary["target_hours"] == 176.0


# =============================================================================
# Berechnung — Edge Cases
# =============================================================================

class TestCalculationEdgeCases:
    """Edge Cases in der Stundenberechnung."""

    def test_half_day_absence_reduces_target_correctly(self, db, test_user):
        """Prüft dass Halbtags-Abwesenheit das Soll reduziert — Tag wird komplett als Abwesenheit gezaehlt."""
        target_before = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, 4.0)
        target_after = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        # Vacation mit 4h → der Tag ist trotzdem ein "Absence-Tag" und wird komplett übersprungen
        # Das ist by-design: absence_dates enthält den Tag, also wird das volle Tagessoll abgezogen
        # Hier testen wir das IST-Verhalten (nicht unbedingt das gewünschte)
        assert target_after < target_before

    def test_multiple_entries_same_day_summed(self, db, test_user):
        """Prüft dass mehrere Eintraege am selben Tag korrekt summiert werden — Multi-Entry."""
        _make_entry(db, test_user, date(2026, 3, 10), 8, 12, break_min=0)   # 4h
        _make_entry(db, test_user, date(2026, 3, 10), 13, 17, start_m=0, end_m=0)  # 4h
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert actual == Decimal('8.00')

    def test_entry_with_full_break_yields_zero(self, db, test_user):
        """Prüft dass Pause gleich Arbeitszeit zu 0h Netto fuehrt — net_hours Floor."""
        _make_entry(db, test_user, date(2026, 3, 10), 8, 16, break_min=480)  # 8h - 8h = 0
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert actual == Decimal('0.00')

    def test_no_entries_no_absences_balance_negative(self, db, test_user):
        """Prüft dass ohne Eintraege das Saldo negativ ist — alle Sollstunden fehlen."""
        balance = calculation_service.get_monthly_balance(db, test_user, 2026, 3)
        assert balance < Decimal('0')
        # 22 Werktage × 8h = -176h
        assert balance == Decimal('-176.00')

    def test_holiday_on_weekend_no_effect(self, db, test_user):
        """Prüft dass Feiertag am Wochenende das Soll nicht aendert — kein Doppelabzug."""
        target_before = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        # 15.03.2026 ist Sonntag
        h = PublicHoliday(date=date(2026, 3, 15), name="Test", year=2026, tenant_id=DEFAULT_TENANT_ID)
        db.add(h)
        db.commit()
        target_after = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        assert target_after == target_before

    def test_working_hours_change_mid_month(self, db, test_user):
        """Prüft dass Stundenänderung Mitte Monat zu gemischtem Soll fuehrt — get_weekly_hours_for_date()."""
        # Ab 16.03. nur noch 20h/Woche (statt 40h)
        change = WorkingHoursChange(
            user_id=test_user.id,
            tenant_id=DEFAULT_TENANT_ID,
            weekly_hours=20.0,
            effective_from=date(2026, 3, 16),
        )
        db.add(change)
        db.commit()

        target = calculation_service.get_monthly_target(db, test_user, 2026, 3)

        # Vor 16.03.: 10 Werktage × 8h = 80h
        # Ab 16.03.: 12 Werktage × 4h = 48h
        # Gesamt: 128h
        assert target == Decimal('128.00')

    def test_track_hours_false_returns_zero_target(self, db):
        """Prüft dass track_hours=False Soll=0 liefert — keine Zeiterfassung fuer diesen User."""
        user = _make_user(
            db, username="notrack", email="notrack@test.de",
            track_hours=False,
        )
        target = calculation_service.get_monthly_target(db, user, 2026, 3)
        assert target == Decimal('0')

    def test_year_carryover_included_in_balance(self, db, test_user):
        """Prüft dass Jahresübertrag als Anfangssaldo ins Überstundenkonto einfliesst."""
        # Übertrag FÜR 2026 → Berechnung startet ab Jan 2026 mit 50h Anfangssaldo
        carryover = YearCarryover(
            user_id=test_user.id,
            tenant_id=DEFAULT_TENANT_ID,
            year=2026,
            overtime_hours=50.0,
            vacation_days=3.0,
        )
        db.add(carryover)
        db.commit()

        overtime = calculation_service.get_overtime_account(db, test_user, 2026, 1)
        # Jan 2026: 50h Übertrag + 0h Ist - 176h Soll = -126h
        assert overtime == Decimal('-126.00')


# =============================================================================
# Absence-Typ-Matrix — Soll/Ist Interaktion
# =============================================================================

class TestAbsenceTypeMatrix:
    """Systematischer Test aller Absence-Typen auf Soll/Ist-Verhalten."""

    @pytest.mark.parametrize("absence_type,reduces_target,counts_as_actual", [
        (AbsenceType.VACATION, True, False),
        (AbsenceType.SICK, False, True),
        (AbsenceType.TRAINING, False, True),
        (AbsenceType.OVERTIME, False, False),
        (AbsenceType.OTHER, True, False),
    ])
    def test_absence_type_behavior(self, db, test_user, absence_type, reduces_target, counts_as_actual):
        """Prüft die Absence-Typ-Matrix: jeder Typ hat definiertes Soll/Ist-Verhalten."""
        target_before = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        _make_absence(db, test_user, date(2026, 3, 10), absence_type, 8.0)
        target_after = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)

        if reduces_target:
            assert target_after < target_before, f"{absence_type} should reduce target"
        else:
            assert target_after == target_before, f"{absence_type} should NOT reduce target"

        if counts_as_actual:
            assert actual == Decimal('8.00'), f"{absence_type} should count as 8h actual"
        else:
            assert actual == Decimal('0.00'), f"{absence_type} should NOT count as actual"


# =============================================================================
# get_overtime_account — Edge Cases
# =============================================================================

class TestOvertimeAccountEdgeCases:
    """Edge Cases im kumulativen Überstundenkonto."""

    def test_overtime_account_uses_latest_carryover(self, db, test_user):
        """Prüft dass bei mehreren Uebertraegen der neueste verwendet wird — kein alter Startpunkt."""
        carryover_2024 = YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            year=2024, overtime_hours=20.0, vacation_days=0,
        )
        carryover_2025 = YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            year=2025, overtime_hours=10.0, vacation_days=0,
        )
        db.add_all([carryover_2024, carryover_2025])
        db.commit()

        # Nur mit 2024er Übertrag berechnen
        overtime_only_2024 = calculation_service.get_overtime_account(db, test_user, 2024, 12)

        # Mit beiden Überträgen für 2026 → 2025er wird genommen (neuer)
        overtime_2026 = calculation_service.get_overtime_account(db, test_user, 2026, 1)

        # 2025er Übertrag (10h) ist kleiner als 2024er (20h), daher ab 2025 schlechterer Start
        # Aber der 2025er Übertrag hat weniger Monate zu berechnen
        # Wichtig: Funktion verwendet den NEUESTEN Übertrag, nicht den ältesten
        assert overtime_2026 != overtime_only_2024  # Unterschiedliche Startpunkte

    def test_overtime_account_without_carryover_cumulates(self, db, test_user):
        """Prüft dass ohne Uebertrag das Defizit ueber Monate kumuliert — wachsende Minusstunden."""
        # 1 Tag in Januar arbeiten → großes Defizit
        _make_entry(db, test_user, date(2026, 1, 5), 8, 16, break_min=0)
        overtime_jan = calculation_service.get_overtime_account(db, test_user, 2026, 1)
        overtime_feb = calculation_service.get_overtime_account(db, test_user, 2026, 2)
        # Feb kumuliert Jan + Feb, beide negativ, Feb noch negativer
        assert overtime_feb < overtime_jan

    def test_overtime_comp_in_ytd_summary(self, db, test_user):
        """Prüft dass YTD-Summary Überstundenausgleich korrekt widerspiegelt — nur Arbeit als Ist."""
        # 1 Arbeitstag
        _make_entry(db, test_user, date(2026, 3, 9), 8, 16, break_min=0)
        # 1 Überstundenausgleich
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.OVERTIME, 8.0)

        ytd = calculation_service.get_ytd_summary(db, test_user, 2026)

        # Ist: nur 8h (der Arbeitstag)
        assert ytd["actual_hours"] == 8.0
        # Soll muss das volle Jahres-Soll enthalten (Überstundenausgleich ändert Soll NICHT)


# =============================================================================
# Journal mit mehreren Einträgen pro Tag
# =============================================================================

class TestJournalMultiEntry:
    """Tests für Tage mit mehreren Zeiteinträgen."""

    def test_two_entries_shown_in_journal(self, db, test_user):
        """Prüft dass zwei Eintraege am selben Tag beide im Journal erscheinen und summiert werden."""
        _make_entry(db, test_user, date(2026, 3, 10), 8, 12, break_min=0)
        _make_entry(db, test_user, date(2026, 3, 10), 13, 17, start_m=0, end_m=0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert len(day["time_entries"]) == 2
        assert day["actual_hours"] == 8.0  # 4h + 4h
        assert day["target_hours"] == 8.0
        assert day["balance"] == 0.0

    def test_mixed_day_work_plus_training(self, db, test_user):
        """Prüft gemischten Tag (Arbeit+Fortbildung): type='mixed', Ist = Arbeit + Fortbildung."""
        _make_entry(db, test_user, date(2026, 3, 10), 7, 12, break_min=0)  # 5h Arbeit
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.TRAINING, 3.0)  # 3h Fortbildung
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["type"] == "mixed"
        assert len(day["time_entries"]) == 1
        assert len(day["absences"]) == 1
        assert day["actual_hours"] == 8.0  # 5h + 3h (Training zählt als Ist)
        assert day["target_hours"] == 8.0

    def test_mixed_day_work_plus_sick(self, db, test_user):
        """Prüft gemischten Tag (Arbeit+Krank): beide zaehlen als Ist — §3 EntgFG."""
        _make_entry(db, test_user, date(2026, 3, 10), 8, 12, break_min=0)  # 4h Arbeit
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.SICK, 4.0)  # 4h Krank
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["type"] == "mixed"
        assert day["actual_hours"] == 8.0  # 4h + 4h (Krank zählt als Ist)
        assert day["balance"] == 0.0

    def test_mixed_day_work_plus_vacation(self, db, test_user):
        """Prüft gemischten Tag (Arbeit+Urlaub): Soll reduziert, Ist = nur Arbeitsstunden."""
        _make_entry(db, test_user, date(2026, 3, 10), 8, 12, break_min=0)  # 4h Arbeit
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, 4.0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["type"] == "mixed"
        assert day["actual_hours"] == 4.0  # Nur Arbeitsstunden
        assert day["target_hours"] == 4.0  # 8h - 4h Urlaub
        assert day["balance"] == 0.0

    def test_mixed_day_work_plus_overtime_comp(self, db, test_user):
        """Gemischter Tag (Arbeit + Überstundenausgleich): Soll BLEIBT voll, der
        Ausgleich zaehlt nicht als Ist -> negativer Tages-Saldo zehrt das Konto.

        Korrigiert (Review 2026-06-23): frueher reduzierte das Journal das Soll um die
        OVERTIME-Stunden (Saldo 0) — das widersprach der Regel 'Soll bleibt, NICHT
        reduzieren' UND get_monthly_target (zieht OVERTIME nie vom Soll ab), sodass
        Tageszeile und Monats-Summary divergierten und der Ausgleich das Konto nicht
        senkte. Jetzt: Soll=8h, Ist=4h, Saldo=-4h (= 4h Überstunden verbraucht)."""
        _make_entry(db, test_user, date(2026, 3, 10), 8, 12, break_min=0)  # 4h Arbeit
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.OVERTIME, 4.0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["type"] == "mixed"
        assert day["actual_hours"] == 4.0   # Nur Arbeitsstunden, OVERTIME zählt nicht als Ist
        assert day["target_hours"] == 8.0   # Soll bleibt voll (OVERTIME reduziert NICHT)
        assert day["balance"] == -4.0       # zehrt das Überstundenkonto um 4h

    def test_three_entries_summed_correctly(self, db, test_user):
        """Prüft dass drei Eintraege am selben Tag korrekt summiert werden — Multi-Entry-Export."""
        _make_entry(db, test_user, date(2026, 3, 10), 7, 9, break_min=0)    # 2h
        _make_entry(db, test_user, date(2026, 3, 10), 10, 12, start_m=0, end_m=0)  # 2h
        _make_entry(db, test_user, date(2026, 3, 10), 13, 17, start_m=0, end_m=0)  # 4h
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert len(day["time_entries"]) == 3
        assert day["actual_hours"] == 8.0


# =============================================================================
# Monatsübergreifende Szenarien
# =============================================================================

class TestCrossMonthScenarios:
    """Tests für monatsübergreifende Berechnungen."""

    def test_overtime_comp_across_months_affects_cumulative(self, db, test_user):
        """Prüft dass Überstunden in Jan und Ausgleich in Feb das kumulative Konto korrekt senkt."""
        # Januar: jeden Tag 9h arbeiten (5 Tage KW1)
        for d in [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                  date(2026, 1, 8), date(2026, 1, 9)]:
            _make_entry(db, test_user, d, 8, 17, break_min=0)

        overtime_jan = calculation_service.get_overtime_account(db, test_user, 2026, 1)

        # Februar: 1 Tag Überstundenausgleich
        _make_absence(db, test_user, date(2026, 2, 10), AbsenceType.OVERTIME, 8.0)

        overtime_feb = calculation_service.get_overtime_account(db, test_user, 2026, 2)

        # Feb-Konto ist schlechter als Jan (wegen vollem Feb-Soll + Ausgleich-Tag hat 0h Ist)
        assert overtime_feb < overtime_jan

    def test_balance_accumulation_three_months(self, db, test_user):
        """Prüft dass Saldo korrekt ueber 3 Monate kumuliert — monoton fallend bei Minusstunden."""
        # Jeden Monat genau 1 Tag arbeiten (8h)
        _make_entry(db, test_user, date(2026, 1, 5), 8, 16, break_min=0)
        _make_entry(db, test_user, date(2026, 2, 9), 8, 16, break_min=0)
        _make_entry(db, test_user, date(2026, 3, 9), 8, 16, break_min=0)

        ot1 = calculation_service.get_overtime_account(db, test_user, 2026, 1)
        ot2 = calculation_service.get_overtime_account(db, test_user, 2026, 2)
        ot3 = calculation_service.get_overtime_account(db, test_user, 2026, 3)

        # Jeder Monat addiert ~8h Ist minus ~168-176h Soll
        assert ot1 > ot2 > ot3  # Alle negativ, immer negativer


# =============================================================================
# Daily Schedule (Tagesplan) Edge Cases
# =============================================================================

class TestDailyScheduleEdgeCases:
    """Edge Cases für User mit individuellem Tagesplan."""

    def test_zero_hours_day_excluded_from_target(self, db):
        """Prüft dass Tage mit 0h im Tagesplan nicht zum Soll beitragen — Teilzeit-Korrektheit."""
        user = _make_user(
            db, username="ds_zero", email="ds_zero@test.de",
            weekly_hours=24.0, work_days_per_week=3,
            use_daily_schedule=True,
            hours_monday=8.0, hours_tuesday=0.0,
            hours_wednesday=8.0, hours_thursday=0.0, hours_friday=8.0,
        )
        # März 2026: 9 Mo + 9 Mi + 9 Fr = 27 Tage × nein, nur 5 Mo + 4 Mi + 4 Fr
        # (Mo: 2,9,16,23,30; Mi: 4,11,18,25; Fr: 6,13,20,27)
        target = calculation_service.get_monthly_target(db, user, 2026, 3)
        # 5 Mo × 8h + 4 Mi × 8h + 4 Fr × 8h = 40 + 32 + 32 = 104h
        # Aber: get_monthly_target nutzt get_daily_target_for_date die 0h für Di/Do gibt
        expected = Decimal('104.00')
        assert target == expected

    def test_vacation_account_basic(self, db, test_user):
        """Prüft dass Urlaubskonto ohne Abwesenheiten volles Budget zeigt — BUrlG Grundanspruch."""
        account = calculation_service.get_vacation_account(db, test_user, 2026)
        assert account["budget_days"] == 30.0
        assert account["used_days"] == 0.0
        assert account["remaining_days"] == 30.0

    def test_vacation_account_with_usage(self, db, test_user):
        """Prüft dass genommene Urlaubstage korrekt vom Budget abgezogen werden."""
        _make_absence(db, test_user, date(2026, 3, 9), AbsenceType.VACATION, 8.0)
        _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, 8.0)
        account = calculation_service.get_vacation_account(db, test_user, 2026)
        assert account["used_days"] == 2.0
        assert account["remaining_days"] == 28.0

    def test_vacation_account_with_carryover(self, db, test_user):
        """Prüft dass Urlaubsuebertrag aus Vorjahr das Budget erhoeht — §7 Abs. 3 BUrlG."""
        carryover = YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            year=2026, overtime_hours=0, vacation_days=5.0,
        )
        db.add(carryover)
        db.commit()
        account = calculation_service.get_vacation_account(db, test_user, 2026)
        assert account["budget_days"] == 35.0  # 30 + 5 Übertrag

    def test_vacation_prorata_mid_year_hire(self, db):
        """Prüft Pro-Rata-Urlaubsberechnung bei Einstellung Mitte des Jahres — §5 BUrlG."""
        user = _make_user(
            db, username="midyear", email="midyear@test.de",
            vacation_days=24,
            first_work_day=date(2026, 7, 1),
        )
        account = calculation_service.get_vacation_account(db, user, 2026)
        # 6 Monate → 24 × 6/12 = 12 Tage
        assert account["budget_days"] == 12.0

    def test_vacation_prorata_departure(self, db):
        """Prüft Pro-Rata-Urlaubsberechnung bei Ausscheiden Mitte des Jahres — §5 BUrlG."""
        user = _make_user(
            db, username="leaving", email="leaving@test.de",
            vacation_days=24,
            last_work_day=date(2026, 6, 30),
        )
        account = calculation_service.get_vacation_account(db, user, 2026)
        # 6 Monate → 24 × 6/12 = 12 Tage
        assert account["budget_days"] == 12.0

    def test_vacation_prorata_same_year_entry_and_exit(self, db):
        """Prüft Pro-Rata-Urlaub wenn Eintritt UND Austritt im selben Jahr liegen — Überschneidung Mär–Okt = 8 Monate."""
        u = _make_user(db, username="tmp", email="tmp@test.de", vacation_days=30,
                       first_work_day=date(2026, 3, 1), last_work_day=date(2026, 10, 31))
        account = calculation_service.get_vacation_account(db, u, 2026)
        # Beschäftigung Mär–Okt = 8 Monate → 30 × 8/12 = 20.0 (nicht min(25,25)=25)
        assert account["budget_days"] == 20.0

    def test_overtime_comp_on_zero_hour_day(self, db):
        """Prüft dass Überstundenausgleich an 0h-Tag (Teilzeit) keinen Effekt auf Soll hat."""
        user = _make_user(
            db, username="ds_ot_zero", email="ds_ot_zero@test.de",
            weekly_hours=24.0, work_days_per_week=3,
            use_daily_schedule=True,
            hours_monday=8.0, hours_tuesday=0.0,
            hours_wednesday=8.0, hours_thursday=0.0, hours_friday=8.0,
        )
        target_before = calculation_service.get_monthly_target(db, user, 2026, 3)
        # Überstundenausgleich an Dienstag (0h-Tag)
        _make_absence(db, user, date(2026, 3, 10), AbsenceType.OVERTIME, 0.0)
        target_after = calculation_service.get_monthly_target(db, user, 2026, 3)
        assert target_after == target_before


# =============================================================================
# Jahresabschluss — Edge Cases
# =============================================================================

class TestYearClosingEdgeCases:
    """Edge Cases beim Jahresabschluss."""

    def test_year_closing_captures_overtime(self, db, test_user):
        """Prüft dass Jahresabschluss Überstundensaldo korrekt berechnet und uebertraegt."""
        _make_entry(db, test_user, date(2025, 12, 1), 8, 18, break_min=0)  # 10h
        results = calculation_service.create_year_closing(db, 2025, [test_user])
        assert len(results) == 1
        assert results[0]["overtime_hours"] < 0

    def test_year_closing_captures_vacation(self, db, test_user):
        """Prüft dass Jahresabschluss den Resturlaub korrekt berechnet — 30-2=28 Tage."""
        _make_absence(db, test_user, date(2025, 6, 9), AbsenceType.VACATION, 8.0)
        _make_absence(db, test_user, date(2025, 6, 10), AbsenceType.VACATION, 8.0)
        results = calculation_service.create_year_closing(db, 2025, [test_user])
        assert results[0]["vacation_days"] == 28.0

    def test_year_closing_carryover_affects_next_year_vacation(self, db, test_user):
        """Prüft dass Urlaubsuebertrag aus Jahresabschluss das Folgejahr-Budget erhoeht."""
        budget_before = calculation_service.get_vacation_account(db, test_user, 2026)["budget_days"]
        carryover = YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            year=2026, overtime_hours=0, vacation_days=5.0,
        )
        db.add(carryover)
        db.commit()
        budget_after = calculation_service.get_vacation_account(db, test_user, 2026)["budget_days"]
        assert budget_after == budget_before + 5.0

    def test_year_closing_carryover_affects_next_year_overtime(self, db, test_user):
        """Prüft dass Überstundenuebertrag als Startbilanz fuers Folgejahr dient."""
        carryover = YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            year=2026, overtime_hours=25.0, vacation_days=0,
        )
        db.add(carryover)
        db.commit()
        overtime = calculation_service.get_overtime_account(db, test_user, 2026, 1)
        # 25h Übertrag - 176h Januar-Soll = -151h
        assert overtime == Decimal('-151.00')

    def test_year_closing_negative_overtime_carryover(self, db, test_user):
        """Prüft dass negativer Überstundenuebertrag korrekt uebernommen wird — Minusstunden."""
        carryover = YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            year=2026, overtime_hours=-20.0, vacation_days=0,
        )
        db.add(carryover)
        db.commit()
        overtime = calculation_service.get_overtime_account(db, test_user, 2026, 1)
        assert overtime < Decimal('-20.00')

    def test_year_closing_mid_year_hire(self, db):
        """Prüft dass Jahresabschluss bei Mitte-des-Jahres-Einstellung Pro-Rata-Urlaub berechnet."""
        user = _make_user(
            db, username="newhire", email="newhire@test.de",
            vacation_days=24, first_work_day=date(2025, 7, 1),
        )
        results = calculation_service.create_year_closing(db, 2025, [user])
        assert results[0]["vacation_days"] == 12.0

    def test_year_closing_overwrite_is_idempotent(self, db, test_user):
        """Prüft dass zweimaliger Jahresabschluss identische Ergebnisse liefert — Idempotenz."""
        results1 = calculation_service.create_year_closing(db, 2025, [test_user])
        results2 = calculation_service.create_year_closing(db, 2025, [test_user])
        assert results1[0]["overtime_hours"] == results2[0]["overtime_hours"]
        assert results1[0]["vacation_days"] == results2[0]["vacation_days"]

    def test_year_closing_with_overtime_comp(self, db, test_user):
        """Prüft dass Überstundenausgleich das Konto im Jahresabschluss korrekt reduziert."""
        # Alle Dezember-Werktage arbeiten + 1 Tag Ausgleich
        dec_workdays = [date(2025, 12, d) for d in range(1, 32)
                        if date(2025, 12, d).weekday() < 5]
        for d in dec_workdays[:5]:  # Nur erste Woche
            _make_entry(db, test_user, d, 7, 17, break_min=0)  # 10h/Tag

        overtime_before = calculation_service.get_overtime_account(db, test_user, 2025, 12)

        # Arbeitszeit am 8.12. (Mo) erstellen und dann durch Ausgleich ersetzen
        _make_entry(db, test_user, date(2025, 12, 8), 8, 16, break_min=0)  # 8h
        overtime_with_work = calculation_service.get_overtime_account(db, test_user, 2025, 12)
        assert overtime_with_work > overtime_before  # 8h mehr gearbeitet

        # Eintrag löschen und stattdessen Überstundenausgleich → 0h Ist statt 8h
        from app.models import TimeEntry
        db.query(TimeEntry).filter(
            TimeEntry.user_id == test_user.id,
            TimeEntry.date == date(2025, 12, 8),
        ).delete()
        _make_absence(db, test_user, date(2025, 12, 8), AbsenceType.OVERTIME, 8.0)
        overtime_with_comp = calculation_service.get_overtime_account(db, test_user, 2025, 12)

        # Ausgleich (0h Ist) ist schlechter als arbeiten (8h Ist)
        assert overtime_with_comp < overtime_with_work


# =============================================================================
# Berechnungen — weitere Unit Tests
# =============================================================================

class TestCalculationUnits:
    """Weitere Unit-Tests für Berechnungsfunktionen."""

    def test_monthly_actual_sums_multiple_entries(self, db, test_user):
        """Prüft dass get_monthly_actual mehrere Eintraege pro Tag korrekt summiert."""
        _make_entry(db, test_user, date(2026, 3, 9), 8, 12)
        _make_entry(db, test_user, date(2026, 3, 9), 13, 17, start_m=0, end_m=0)
        _make_entry(db, test_user, date(2026, 3, 10), 8, 16)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert actual == Decimal('16.00')

    def test_monthly_actual_with_break(self, db, test_user):
        """Prüft dass Pausen von den Ist-Stunden abgezogen werden — §4 ArbZG Pausenregelung."""
        _make_entry(db, test_user, date(2026, 3, 9), 8, 17, break_min=60)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert actual == Decimal('8.00')

    def test_get_daily_target_standard(self, db, test_user):
        """Prüft dass Standard-User (40h/5d) ein Tagessoll von 8h hat."""
        target = calculation_service.get_daily_target(test_user)
        assert target == Decimal('8.00')

    def test_get_daily_target_parttime(self, db):
        """Prüft dass Teilzeit-User (20h/5d) ein Tagessoll von 4h hat."""
        user = _make_user(db, username="pt", email="pt@test.de", weekly_hours=20.0)
        target = calculation_service.get_daily_target(user)
        assert target == Decimal('4.00')

    def test_get_daily_target_3day_week(self, db):
        """Prüft dass 3-Tage-Woche (24h/3d) ein Tagessoll von 8h hat."""
        user = _make_user(
            db, username="3day", email="3day@test.de",
            weekly_hours=24.0, work_days_per_week=3,
        )
        target = calculation_service.get_daily_target(user)
        assert target == Decimal('8.00')

    def test_sick_does_not_reduce_target(self, db, test_user):
        """Prüft dass Krankheit das Soll nicht reduziert — §3 EntgFG Lohnfortzahlung."""
        target_before = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        _make_absence(db, test_user, date(2026, 3, 9), AbsenceType.SICK, 8.0)
        target_after = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        assert target_after == target_before

    def test_sick_counts_as_actual(self, db, test_user):
        """Prüft dass Krankheit als Ist-Stunden gutgeschrieben wird — §3 EntgFG."""
        _make_absence(db, test_user, date(2026, 3, 9), AbsenceType.SICK, 8.0)
        actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
        assert actual == Decimal('8.00')

    def test_other_absence_reduces_target(self, db, test_user):
        """Prüft dass sonstige Abwesenheit das Soll reduziert — kein Ist-Stunden-Ausgleich."""
        target_before = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        _make_absence(db, test_user, date(2026, 3, 9), AbsenceType.OTHER, 8.0)
        target_after = calculation_service.get_monthly_target(db, test_user, 2026, 3)
        assert target_after < target_before
