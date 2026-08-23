"""#449: N+1 im Datei-Export + Monatsjournal — Vertrags-Snapshot pro Tag.

Alle Export-Tagesschleifen (XLSX-Monatsblatt, XLSX-Jahres-Mitarbeiterblatt,
PDF-Monat, die beiden ODS-Pendants) sowie ``journal_service.get_journal`` riefen
``calculation_service.get_schedule_for_date(db, user, tag)`` PRO TAG ohne den
``wh_changes``-Preload auf, obwohl der Parameter an allen beteiligten Funktionen
bereits existiert (#431) — macht bei einem Jahresbericht ~365 statt 1 SELECT auf
``working_hours_changes`` je Mitarbeitendem. ``export_service.absence_day_target``
/ die journal-lokale ``_absence_day_target`` haben denselben Preload-Parameter,
wurden an ihren fünf Aufrufstellen aber ebenfalls ohne ihn aufgerufen (an jedem
Tag MIT Abwesenheit eine weitere Einzelquery).

Zusätzlich gefunden (derselbe Bug in derselben Funktionsfamilie):
``calculation_service.get_vacation_account`` akzeptiert ebenfalls einen
``wh_changes``-Preload und nutzt ihn intern in einer Schleife über die
VACATION-Absencen des Jahres — die Zusammenfassungs-Sektionen der
Employee-Sheets riefen ihn aber ohne diesen Preload auf, macht also eine
Einzelquery PRO VACATION-ABSENCE. Gefixt an allen vier Stellen, an denen der
Preload aus der Tagesschleife bereits in Scope ist (siehe CLAUDE.md
"Fundstellen"). Die beiden Personen-Loop-Übersichtsblätter (Jahresübersicht/
Abwesenheiten-Übersicht in XLSX + ODS) rufen ``get_vacation_account`` ebenso
ungefixt auf — bewusst NICHT angefasst, siehe Bericht (anderer Loop-Typ, kein
existierender Preload in Scope, nicht in den vom Ticket benannten Flächen).

Die Query-Zahl je Report ist NICHT 1: dieselbe Employee-Sheet-Funktion ruft am
Ende noch ``get_monthly_target``/``get_monthly_actual``/``get_overtime_account``
für die Zusammenfassung auf — jede davon hat schon vor #449 ihren EIGENEN
internen (korrekten, O(1)) WorkingHoursChange-Preload. Der richtige
Prüfmaßstab ist deshalb nicht "== 1", sondern INVARIANZ: die Query-Zahl darf
sich nicht ändern, wenn sich die Anzahl der Tage/Abwesenheiten im
Report-Zeitraum ändert (28 vs. 31 Tage, 0 vs. 2 Abwesenheitstage) — vorher
wuchs sie linear mit; nachher ist sie konstant je Mitarbeitendem. Die beiden
Jahres-Tests rufen dafür das jeweilige Employee-Sheet DIREKT auf (nicht den
``generate_yearly_report``-Wrapper), um die bewusst unveränderten
Übersichtsblätter aus der Messung herauszuhalten.

Rein mechanisch, kein Verhaltenswechsel: ``get_schedule_for_date``/
``_day_soll_contribution`` mit vs. ohne ``wh_changes`` sind laut #431/Fix-Welle-4
bereits als byte-identisch erwiesen (``test_calc_preload.py`` u.a.) — dieser Test
beweist zusätzlich, dass die hier geänderten Aufrufer (a) die Query-Zahl
tag-/abwesenheits-UNABHÄNGIG machen und (b) dabei exakt dieselben Werte liefern
wie eine Referenzrechnung direkt über ``calculation_service`` (unabhängig vom
Preload-Pfad).
"""
from datetime import date, time

import pytest
from sqlalchemy import event

from app.models import Absence, AbsenceType, PublicHoliday, TimeEntry, WorkingHoursChange
from app.services import calculation_service, export_service, ods_export_service, journal_service
from tests.conftest import DEFAULT_TENANT_ID, engine


class _WhQueryCounter:
    """Zaehlt SELECTs gegen working_hours_changes waehrend des with-Blocks
    (Muster: test_fix_wave4_wh_preload.py)."""

    def __init__(self):
        self.count = 0

    def __enter__(self):
        def _listener(conn, cursor, statement, parameters, context, executemany):
            if "from working_hours_changes" in statement.lower():
                self.count += 1
        self._listener = _listener
        event.listen(engine, "before_cursor_execute", _listener)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._listener)


@pytest.fixture
def wh_history(db, test_user):
    """Eine Wochenstunden-Aenderung MITTEN im Testzeitraum (2026-05-16), damit
    get_schedule_for_date fuer Mai tatsaechlich zwei unterschiedliche Segmente
    aufloesen muss. Dazu EIN Zeiteintrag im Januar: ``get_overtime_account``
    (in jeder Summary-Sektion aufgerufen) sucht ohne YearCarryover den
    FRUEHESTEN TimeEntry ueber den GESAMTEN Nutzer und ueberspringt seinen
    eigenen (unveraenderten, korrekten) internen WHChange-Preload komplett,
    wenn gar kein Eintrag existiert (frueher Return 0). Ohne diesen Baseline-
    Eintrag wuerde ein Query-Count-Vergleich "0 Zeiteintraege" gegen "1+
    Zeiteintraege" scheinbar zusaetzliche WHChange-Queries zeigen, die aber
    NICHTS mit #449 zu tun haben (siehe Modul-Docstring) — der Baseline-Eintrag
    haelt diesen Seiteneffekt in ALLEN Vergleichen konstant."""
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
        weekly_hours=20.0, effective_from=date(2026, 5, 16),
    ))
    db.add(TimeEntry(
        user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 1, 5),
        start_time=time(8, 0), end_time=time(16, 0), break_minutes=30,
    ))
    db.commit()
    return test_user


def _add_may_absences_and_entries(db, user):
    """Fuegt user einen Arbeitstag + einen Halbtags-Urlaub + einen Krankentag
    im Mai hinzu — uebt absence_day_target()/_absence_day_target() an zwei
    Tagen aus (die zweite gefixte Stelle neben dem reinen Tages-Soll)."""
    db.add(TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 5, 4),
        start_time=time(8, 0), end_time=time(16, 0), break_minutes=30,
    ))
    db.add(Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 5, 11),
        type=AbsenceType.VACATION, hours=4.0, half_day=True,
    ))
    db.add(Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 5, 12),
        type=AbsenceType.SICK, hours=8.0,
    ))
    db.add(PublicHoliday(date=date(2026, 5, 1), name="Tag der Arbeit", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def _ground_truth_target(db, user, d):
    """Referenzwert unabhaengig vom Preload-Pfad: get_schedule_for_date ohne
    wh_changes (alter Query-pro-Tag-Pfad) muss dasselbe liefern."""
    schedule = calculation_service.get_schedule_for_date(db, user, d)
    return calculation_service.get_daily_target_for_date(user, d, schedule)


class TestXlsxMonthlyPreload:
    def test_query_count_independent_of_days_and_absences(self, db, wh_history):
        """Februar (28 Tage, 0 Abwesenheiten) vs. Mai (31 Tage, 2 Abwesenheiten
        + 1 Zeiteintrag) muessen exakt gleich viele WHChange-Queries kosten —
        vorher waechst die Zahl mit jedem zusaetzlichen Tag/jeder Abwesenheit,
        nachher ist sie konstant je Mitarbeitendem."""
        with _WhQueryCounter() as short:
            export_service.generate_monthly_report(db, 2026, 2)

        _add_may_absences_and_entries(db, wh_history)
        with _WhQueryCounter() as long_:
            export_service.generate_monthly_report(db, 2026, 5)

        assert short.count > 0, "Testaufbau fehlerhaft: gar keine WHChange-Query gemessen"
        assert long_.count == short.count, (
            f"WHChange-Queries wachsen mit Tagen/Abwesenheiten "
            f"({short.count} -> {long_.count}) — nicht mehr O(1)?"
        )

    def test_daily_target_matches_ground_truth_across_wh_change(self, db, wh_history):
        """Tag VOR und Tag NACH der Wochenstunden-Aenderung: der vorgeladene
        Pfad muss exakt denselben Tageswert liefern wie die Einzel-Query
        (byte-identisch, #431-Garantie)."""
        before_change = date(2026, 5, 4)   # noch 40h-Woche
        after_change = date(2026, 5, 18)   # schon 20h-Woche

        expected_before = _ground_truth_target(db, wh_history, before_change)
        expected_after = _ground_truth_target(db, wh_history, after_change)
        assert expected_before != expected_after, "Testaufbau fehlerhaft: WH-Aenderung wirkt nicht"

        preloaded = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == wh_history.id,
            WorkingHoursChange.tenant_id == wh_history.tenant_id,
        ).order_by(WorkingHoursChange.effective_from).all()

        sched_before = calculation_service.get_schedule_for_date(db, wh_history, before_change, wh_changes=preloaded)
        sched_after = calculation_service.get_schedule_for_date(db, wh_history, after_change, wh_changes=preloaded)
        got_before = calculation_service.get_daily_target_for_date(wh_history, before_change, sched_before)
        got_after = calculation_service.get_daily_target_for_date(wh_history, after_change, sched_after)

        assert got_before == expected_before
        assert got_after == expected_after


class TestXlsxYearlyPreload:
    def test_query_count_independent_of_absences(self, db, wh_history):
        """Ruft ``_create_employee_yearly_sheet`` DIREKT auf (nicht den
        ``generate_yearly_report``-Wrapper): der Wrapper haengt zusaetzlich
        eine Jahresuebersicht + eine Abwesenheits-Uebersicht ueber ALLE
        Mitarbeitenden an (Personen-Loop, kein Tages-Loop) — diese haben
        keinen eigenen Preload und sind bewusst NICHT Teil dieses Fixes (siehe
        Bericht). Der direkte Aufruf isoliert exakt die gefixte Flaeche."""
        from openpyxl import Workbook
        wb1 = Workbook()
        with _WhQueryCounter() as short:
            export_service._create_employee_yearly_sheet(wb1, db, wh_history, 2026)

        _add_may_absences_and_entries(db, wh_history)
        wb2 = Workbook()
        with _WhQueryCounter() as long_:
            export_service._create_employee_yearly_sheet(wb2, db, wh_history, 2026)

        assert short.count > 0
        assert long_.count == short.count, (
            f"WHChange-Queries wachsen mit Abwesenheiten ({short.count} -> {long_.count})"
        )


class TestPdfMonthlyPreload:
    def test_query_count_independent_of_days_and_absences(self, db, wh_history):
        with _WhQueryCounter() as short:
            export_service.generate_monthly_report_pdf(db, 2026, 2)

        _add_may_absences_and_entries(db, wh_history)
        with _WhQueryCounter() as long_:
            export_service.generate_monthly_report_pdf(db, 2026, 5)

        assert short.count > 0
        assert long_.count == short.count, (
            f"WHChange-Queries wachsen mit Tagen/Abwesenheiten ({short.count} -> {long_.count})"
        )


class TestOdsMonthlyPreload:
    def test_query_count_independent_of_days_and_absences(self, db, wh_history):
        with _WhQueryCounter() as short:
            ods_export_service.generate_monthly_report(db, 2026, 2)

        _add_may_absences_and_entries(db, wh_history)
        with _WhQueryCounter() as long_:
            ods_export_service.generate_monthly_report(db, 2026, 5)

        assert short.count > 0
        assert long_.count == short.count, (
            f"WHChange-Queries wachsen mit Tagen/Abwesenheiten ({short.count} -> {long_.count})"
        )


class TestOdsYearlyPreload:
    def test_query_count_independent_of_absences(self, db, wh_history):
        """Ruft ``_yearly_employee_sheet`` DIREKT auf — derselbe Grund wie bei
        der XLSX-Jahresvariante (der ``generate_yearly_report``-Wrapper haengt
        zwei Personen-Loop-Uebersichtsblaetter ohne eigenen Preload an, die
        bewusst nicht Teil dieses Fixes sind, siehe Bericht)."""
        doc1, bold1, _ = ods_export_service._doc_with_styles()
        with _WhQueryCounter() as short:
            ods_export_service._yearly_employee_sheet(doc1, db, wh_history, 2026, bold1)

        _add_may_absences_and_entries(db, wh_history)
        doc2, bold2, _ = ods_export_service._doc_with_styles()
        with _WhQueryCounter() as long_:
            ods_export_service._yearly_employee_sheet(doc2, db, wh_history, 2026, bold2)

        assert short.count > 0
        assert long_.count == short.count, (
            f"WHChange-Queries wachsen mit Abwesenheiten ({short.count} -> {long_.count})"
        )


class TestJournalPreload:
    def test_query_count_independent_of_days_and_absences(self, db, wh_history):
        with _WhQueryCounter() as short:
            journal_service.get_journal(db, wh_history, 2026, 2)

        _add_may_absences_and_entries(db, wh_history)
        with _WhQueryCounter() as long_:
            journal_service.get_journal(db, wh_history, 2026, 5)

        assert short.count > 0
        assert long_.count == short.count, (
            f"WHChange-Queries wachsen mit Tagen/Abwesenheiten ({short.count} -> {long_.count})"
        )

    def test_journal_days_match_ground_truth_across_wh_change(self, db, wh_history):
        """Der Preload darf die zurueckgegebenen Tageswerte nicht veraendern —
        Stichprobe auf beiden Seiten der Wochenstunden-Aenderung."""
        _add_may_absences_and_entries(db, wh_history)
        result = journal_service.get_journal(db, wh_history, 2026, 5)
        days_by_date = {d["date"]: d for d in result["days"]}

        for d in (date(2026, 5, 4), date(2026, 5, 18)):
            expected = _ground_truth_target(db, wh_history, d)
            got = days_by_date[d.isoformat()]["target_hours"]
            assert got == pytest.approx(float(expected), abs=1e-6)
