from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional, Set
from datetime import date, timedelta
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, Absence, AbsenceType, PublicHoliday, CompanyClosure, TimeEntry, WorkingHoursChange, TimeEntryAuditLog
from app.services import calculation_service, settings_service, special_days_service
# Fix #3: the year re-split lives in a service module so the private-vacation
# write paths can call it without importing this router (circular-import safe).
# Re-exported as _resplit_year_closures to keep the existing call sites intact.
from app.services.closure_split_service import resplit_year_closures as _resplit_year_closures
from app.routers.admin_helpers import _create_audit_log, lock_user_rows


# Release-Review 1.16.0: Betriebsferien löschen Abwesenheiten (beim Umspeichern und
# beim Entfernen der Schließung) — bisher spurlos, während `absences.delete_absence`
# vor jeder Löschung einen Audit-Eintrag schreibt. Für DSGVO Art. 5 Abs. 2 und §16
# ArbZG muss nachvollziehbar bleiben, wer wann wie viele generierte Abwesenheiten
# entfernt hat. Eine Summenzeile pro Vorgang statt einer pro Abwesenheit: die
# Zuordnung steckt in `closure_id`/Note, und ein Voll-Jahr-Umspeichern würde die
# Audit-Tabelle sonst mit hunderten Zeilen fluten.
# Marker < 40 Zeichen (time_entry_audit_logs.source ist varchar(40)).
CLOSURE_AUDIT_SOURCE = "company_closure"  # 15 Zeichen


def _audit_closure_absence_deletion(db, current_user, closure, count: int, reason: str) -> None:
    """Summen-Audit für gelöschte Betriebsferien-Abwesenheiten (No-op bei 0)."""
    if not count:
        return
    db.add(TimeEntryAuditLog(
        time_entry_id=None,
        user_id=current_user.id,
        changed_by=current_user.id,
        action="delete",
        source=CLOSURE_AUDIT_SOURCE,
        old_note=(
            f"Betriebsferien '{closure.name}' "
            f"({closure.start_date.isoformat()}–{closure.end_date.isoformat()}): "
            f"{count} generierte Abwesenheit(en) gelöscht — {reason}"
        ),
        tenant_id=current_user.tenant_id,
    ))


router = APIRouter(prefix="/api/company-closures", tags=["company-closures"])


class CompanyClosureCreate(BaseModel):
    # Spalte company_closures.name ist String(255) (Release-Review 1.20.1).
    name: str = Field(..., min_length=1, max_length=255)
    start_date: date
    end_date: date
    # #145: True (default) -> generated absences are VACATION (deduct the
    # vacation budget, legacy behaviour). False -> PAID_LEAVE (paid leave,
    # like a holiday: reduces target, no vacation deduction, balance-neutral).
    counts_as_vacation: bool = True


class CompanyClosureUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    start_date: date
    end_date: date
    counts_as_vacation: bool = True


class CompanyClosureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    start_date: date
    end_date: date
    created_by: str
    counts_as_vacation: bool = True
    affected_employees: int = 0
    # Gesamtreview 1.20 B5 (Nachzug): Anlegen/Ändern, das Buchungen in einem
    # Jahr mit Jahresabschluss ändert, meldet den veralteten Übertrag — wie das
    # Löschen (Fix #5, dort 200 + {"warning"}). Sonst None.
    warning: Optional[str] = None


def _closure_booking_state(db: Session, closure_id, tenant_id) -> set:
    """Die Buchungen einer Schließung als vergleichbare Menge
    ``(user_id, date, type, hours)`` — Grundlage der Jahresabschluss-Warnung von
    ``create_closure``/``update_closure``. Bewusst ohne ``note``/``end_date``:
    ein Umbenennen ändert keinen Saldo und kein Urlaubskonto. Die
    #314-Neuaufteilung löscht und bucht beim Neuspeichern neu; bleibt dabei
    alles gleich, ist die Menge identisch und es gibt nichts zu melden."""
    return {
        (a.user_id, a.date, a.type, float(a.hours))
        for a in db.query(Absence).filter(
            Absence.closure_id == closure_id,
            Absence.tenant_id == tenant_id,  # F-026
        ).all()
    }


def _closed_year_warning_for_changes(db: Session, tenant_id, before: set, after: set) -> Optional[str]:
    """Warnung, wenn sich eine Buchung der Schließung in einem bereits
    abgeschlossenen Jahr geändert hat (Gesamtreview 1.20 B5, Nachzug).

    Der Jahresabschluss ist ein eingefrorener Übertrag (``YearCarryover`` Y+1,
    ``source='year_closing'``, s. ``closed_years_in_range``)
    und wird bewusst nie automatisch neu berechnet (Fix #5). Beim Löschen einer
    Schließung meldete ``delete_closure`` das schon immer; Anlegen und Ändern
    schwiegen — etwa beim Neuspeichern, das 0-h-Altbestand abräumt (Elternzeit
    über den Jahreswechsel: der Resturlaub des abgeschlossenen Jahres steigt, der
    Übertrag bleibt). Gemeldet wird nur, was sich tatsächlich geändert hat.
    """
    changed_years = {d.year for (_, d, _, _) in before ^ after}
    if not changed_years:
        return None
    return calculation_service.stale_year_closing_warning(db, tenant_id, changed_years)


def _get_workdays(start: date, end: date, holidays: set) -> List[date]:
    """Return all workdays (Mon-Fri, excl. holidays) in range."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            days.append(current)
        current += timedelta(days=1)
    return days


def _get_holidays_for_range(db: Session, start: date, end: date, tenant_id) -> set:
    # F-026: PublicHoliday is tenant-scoped — always filter by tenant_id
    # (CLAUDE.md: holidays are loaded standalone, no RLS coverage here).
    years = set(range(start.year, end.year + 1))
    holidays = set()
    for year in years:
        year_holidays = db.query(PublicHoliday).filter(
            PublicHoliday.year == year,
            PublicHoliday.tenant_id == tenant_id,
        ).all()
        holidays.update([h.date for h in year_holidays])
    return holidays


def _lock_participant_rows(db: Session, tenant_id, user_ids) -> None:
    """Audit 2026-07-31 (A2): Anker-Sperre auf den Mitarbeiter-Zeilen.

    Betriebsferien sind ein Absence-BUCHUNGSpfad. Die Vorab-Existenzprüfung
    (``existing_keys``) liest ungesperrt; eine gleichzeitige Direkt-Buchung
    (``absences.create_absence``) oder Antrags-Genehmigung könnte am selben Tag
    einen ANDEREN Typ einfügen — das UNIQUE ist ``(tenant, user, date, TYPE)``
    und fängt das nicht. Die Benutzerzeile ist der gemeinsame Anker aller
    Buchungspfade.

    Die Sperren werden nach ``User.id`` SORTIERT in EINER Anweisung geholt.

    ZUSICHERUNG (und ihre Vorbedingung — Abschluss-Review 2026-07-31):
    Zwei gleichzeitige Betriebsferien-Vorgänge können sich nur dann nicht
    verklemmen, wenn beide diese Anweisung absetzen, BEVOR sie irgendetwas
    schreiben. Grund: die Anker-Sperren schließen sich gegenseitig aus; wer
    zuerst einen Teil davon greift und den Rest später nachholt, kann sich mit
    einem gleichzeitigen Vorgang über Kreuz verklemmen. Genau so lief es bis
    zum Abschluss-Review in ``create_closure`` (die Schließungszeile wurde vor
    dem Anker geflusht) — reproduziert in
    ``tests/test_concurrency.py::test_two_parallel_closure_creations_do_not_deadlock``.
    Deshalb gilt für ALLE Aufrufer: erst sperren, dann schreiben, und die
    Menge muss JEDE Benutzerzeile enthalten, die der Vorgang danach EXPLIZIT
    sperrt.

    Die Zeile des handelnden Admins (``created_by``) bleibt in der Menge der
    Aufrufer. Seit die Anker ``FOR NO KEY UPDATE`` sind (Audit 2026-07-31,
    Restklasse — siehe ``admin_helpers.lock_user_rows``), ist sie dafür nicht
    mehr ZWINGEND: der implizite ``FOR KEY SHARE`` des ``created_by``-INSERTs
    kollidiert nicht mehr mit einem Anker. Sie bleibt trotzdem drin, weil der
    Admin über ``receives_company_closures`` in aller Regel ohnehin Teilnehmer
    ist und die Menge damit ehrlich beschreibt, wessen Buchungen dieser Vorgang
    serialisiert.

    Weil vor Abschluss dieser Anweisung keine Absence-Sperre gehalten wird,
    bleibt zugleich die globale Reihenfolge Benutzer → Abwesenheit gegenüber
    den Einzel-Buchungspfaden gewahrt.
    """
    lock_user_rows(db, tenant_id, user_ids)


def _create_closure_absences(
    db: Session,
    closure: CompanyClosure,
    workdays: List[date],
    employees: List[User],
    current_user: User,
    delete_time_entries: bool = True,
) -> int:
    """Create the closure absences linked to ``closure`` for the given workdays.

    The absence ``type`` follows the closure's ``counts_as_vacation`` flag
    (#145): VACATION when the days should deduct the vacation budget (legacy
    default), PAID_LEAVE when they are paid leave like a holiday (no vacation
    deduction, balance-neutral, target reduced to 0).

    #314: when ``closure_overtime_after_vacation`` is enabled AND the closure
    counts as vacation, days are booked chronologically — first as VACATION while
    the per-year remaining budget covers a full day, then as OVERTIME
    (Überstundenabbau, no minus-vacation; the overtime account may go negative).

    Mirrors the create-time logic: skips any day where the employee already
    has an absence (Fremd-Absence wird nicht überschrieben), deletes existing
    time entries on covered days (with audit log) and credits the
    per-day target via the authoritative weekly_hours lookup.

    Returns the number of distinct employees that received at least one new
    absence.
    """
    absence_type = (
        AbsenceType.VACATION if closure.counts_as_vacation else AbsenceType.PAID_LEAVE
    )
    # Fix #6 (by design — NO remaining_days cap): Betriebsferien are MANDATORY
    # leave (Pflichturlaub) and are always booked, even past the vacation budget.
    # With the toggle OFF this can produce minus-vacation; with it ON the surplus
    # becomes Überstundenausgleich (see split below). This is the INTENDED
    # difference to the direct/approval paths (create_absence /
    # review_vacation_request), which DO cap hard with a 400 — an employee can't
    # voluntarily overdraw, but the employer can impose closure leave.
    # #314: global toggle — when a *vacation* closure exceeds an employee's
    # remaining vacation budget, book the surplus days as OVERTIME
    # (Überstundenausgleich → reduces the overtime account, may go negative)
    # instead of producing minus-vacation. Chronological: vacation first, then
    # overtime. Off (default) = legacy behaviour (all VACATION).
    split_overtime = closure.counts_as_vacation and settings_service.get_bool_setting(
        db, "closure_overtime_after_vacation", current_user.tenant_id, False
    )
    # consume the budget earliest-first
    workdays = sorted(workdays)
    affected = 0

    # #394 / Teil B: on reduced days the closure books the reduced target and
    # consumes only HALF a vacation day (customer report philvdb): `half_day`
    # (24./31.12. as "halber Feiertag") books 0.5 × t, `max_hours` (24./31.12.
    # "verkürzt" and the verkürzte Tage of ``reduced_days``) books min(t, X) —
    # both via ``special_day_target``; the 0.5-day consumption comes from
    # ``half_special_day_weight``. `free` special days have target 0 and are
    # excluded from `workdays` upstream.
    # Config is per-year, shared across all employees → load once.
    special_cfg_by_year = {
        yr: special_days_service.get_special_day_config(db, current_user.tenant_id, yr)
        for yr in {d.year for d in workdays}
    }

    # #204: Statt ~3 Queries pro (MA × Arbeitstag) — bei z. B. 40 MA × 15 Tagen
    # ~1.800 SELECTs — die Referenzdaten in je EINER Query vorladen und in-memory
    # nachschlagen. Logik unveraendert.
    emp_ids = [e.id for e in employees]
    existing_keys = set()
    te_by_key: dict = {}
    wh_by_user: dict = {}
    if emp_ids:
        # Audit 2026-07-31 (A2): Anker-Sperre VOR der Existenz-Vorabfrage —
        # Reihenfolge Benutzer → Abwesenheit (siehe _lock_participant_rows).
        # Beide Aufrufer holen sie inzwischen schon selbst, bevor sie irgendetwas
        # schreiben (``create_closure`` vor dem INSERT der Schließungszeile,
        # ``update_closure`` vor den Löschungen); ein erneuter Erwerb derselben
        # Zeilen in derselben Transaktion ist ein No-op. Der Aufruf bleibt als
        # Rückfallebene für künftige Aufrufer stehen — er darf aber NIE die
        # einzige Sperre sein, wenn vorher schon geschrieben wurde (siehe die
        # Zusicherung im Docstring von ``_lock_participant_rows``).
        _lock_participant_rows(db, current_user.tenant_id, emp_ids)
        existing_keys = {
            (a.user_id, a.date)
            for a in db.query(Absence.user_id, Absence.date).filter(
                Absence.user_id.in_(emp_ids),
                Absence.tenant_id == current_user.tenant_id,
                Absence.date.in_(workdays),
            ).all()
        }
        for entry in db.query(TimeEntry).filter(
            TimeEntry.user_id.in_(emp_ids),
            TimeEntry.tenant_id == current_user.tenant_id,
            TimeEntry.date.in_(workdays),
        ).all():
            te_by_key.setdefault((entry.user_id, entry.date), []).append(entry)
        wh_by_user.update(calculation_service.wh_changes_by_user(
            db, current_user.tenant_id, emp_ids))

    for employee in employees:
        created_for_employee = False
        emp_wh = wh_by_user.get(employee.id, [])
        # #314: remaining vacation budget snapshot per year (Decimal, like the
        # re-split in closure_split_service), consumed as we book VACATION days;
        # once exhausted the surplus days become OVERTIME.
        remaining_by_year: dict = {}
        for workday in workdays:
            # #298: never book closure absences OUTSIDE the employee's employment
            # window. A future-start employee (first_work_day in the future, e.g. an
            # Azubine starting on 1.9.) or an already-departed one (after last_work_day)
            # must not receive VACATION/PAID_LEAVE for days she is not employed —
            # otherwise a vacation-deducting Betriebsferien shows her with "genommene
            # Urlaubstage" today, before she has even started. Mirrors the per-day
            # employment-window guard from #193/#195 (which only covered the calc
            # loops + the #290 new-user enrol path, not the closure-booking itself).
            if not calculation_service._within_employment_window(employee, workday):
                continue

            # F-027/#204 + #431: authoritative Vertrags-Snapshot je Datum
            # (get_daily_target_for_date darf NIE auf die aktuellen User-Felder
            # zurückfallen; wh_changes ist vorgeladen).
            schedule = calculation_service.get_schedule_for_date(
                db, employee, workday, wh_changes=emp_wh
            )
            day_target = calculation_service.get_daily_target_for_date(
                employee, workday, schedule
            )
            # #314 (philvdb): an einem Nicht-Arbeitstag eines Tagesplan-
            # Teilzeitlers (Tagessoll 0 an diesem Wochentag) gibt es nichts zu
            # schließen — KEINE Buchung (sonst eine irreführende 0h-„Urlaub"-Zeile).
            # Vor der TimeEntry-Löschung, damit an einem solchen Tag nichts angefasst
            # wird. Untracked/leitende (track_hours=False → Tagessoll immer 0) NICHT
            # skippen: die bekommen tagebasiert 1 Urlaubstag pro Closure-Tag (#191).
            # #431: der Modus kommt aus dem oben zum DATUM aufgelösten Snapshot,
            # NICHT vom Live-Flag der User-Zeile. Sonst griff der Skip nicht, wenn
            # der MA heute gleichmäßig geführt wird, zum Closure-Datum aber im
            # Tagesplan stand — und der Create-Pfad löschte unten geleistete
            # Arbeitszeit an einem Tag, an dem gar nicht zu schließen war.
            # Gesamtreview 1.20 B5: in BEIDEN Modi — auch ein gleichmaessiger
            # Vertrag kann 0 Wochenstunden tragen (Schema ge=0, z. B. Elternzeit).
            # Vorher entstand dort je Schliesstag eine 0-h-„Urlaub"-Zeile; steht
            # der Vertrag HEUTE auf 0 h, zaehlt das Urlaubskonto ohne Tagessoll
            # jede davon als ganzen Urlaubstag (die Elternzeit verlor Urlaub an die
            # Betriebsferien). Deckungsgleich mit
            # ``calculation_service.is_vacation_billable_day`` (ruft ihn aus
            # Perf-Gruenden nicht selbst auf, der Snapshot liegt schon vor).
            if schedule.track_hours and day_target <= 0:
                continue

            # Skip if any absence already exists for this day (not just vacation)
            if (employee.id, workday) in existing_keys:
                continue

            day_entries = te_by_key.get((employee.id, workday), [])

            # #290: On a re-save / backfill (delete_time_entries=False) we must
            # NEVER silently destroy a participant's logged work. If the day
            # already holds a real time entry, the employee demonstrably worked
            # despite the closure → leave it untouched and do NOT book a closure
            # absence over it (work wins; no double-counting). Only the initial
            # create path (default True) replaces pre-existing entries.
            if day_entries and not delete_time_entries:
                continue

            # Delete existing time entries on this day with audit log
            if delete_time_entries:
                for entry in day_entries:
                    _create_audit_log(
                        db, entry.id, employee.id, current_user.id,
                        action="delete", old_entry=entry,
                        source="company_closure",
                        tenant_id=current_user.tenant_id,
                    )
                    db.delete(entry)

            # #394 / Teil B: on a reduced day (`half_day` or `max_hours`) the closure
            # books the reduced target (hours = special_day_target, half_day=False)
            # and consumes 0.5 day via half_special_day_weight (same helper as
            # get_vacation_account and the budget checks).
            sd_cfg = special_cfg_by_year[workday.year]
            if special_days_service.special_day_mode(workday, sd_cfg) == special_days_service.MODE_FREE:
                continue  # `free` day — defensive; already excluded from workdays
            booked_target = special_days_service.special_day_target(workday, day_target, sd_cfg)
            day_consumption = calculation_service.half_special_day_weight(workday, sd_cfg)

            # #314: decide VACATION vs OVERTIME per day. VACATION while the
            # remaining budget covers this day's consumption; afterwards OVERTIME
            # (no minus-vacation). Only positive-target days consume the snapshot.
            # The split only makes sense on time-tracked days: on a day without
            # hour tracking (track_hours=False laut Snapshot, daily target 0) there
            # is no overtime account, so an OVERTIME day would vanish from all
            # accounting. Such days stay VACATION but consume the budget by day,
            # exactly like the re-split (``resplit_year_closures``) — Teil A:
            # decided per workday from the snapshot, never from the user column.
            day_type = absence_type
            if split_overtime and (day_target > 0 or not schedule.track_hours):
                yr = workday.year
                if yr not in remaining_by_year:
                    # Resturlaub des Jahres als TAGE-Budget (Tagesprinzip). Die
                    # closure-eigenen Tage sind beim Re-Save vorher gelöscht+geflusht
                    # bzw. beim Create noch nicht vorhanden → der Snapshot zählt sie
                    # nicht doppelt. So zehrt die Closure den VERBLEIBENDEN Urlaub
                    # chronologisch bis 0 auf, der Rest wird Überstundenausgleich —
                    # NIE Minus-Urlaub, auch wenn SPÄTER im Jahr Urlaub (z. B. Sommer)
                    # gebucht ist (der zählt korrekt mit; #314 Folgefix-Review).
                    remaining_by_year[yr] = Decimal(str(
                        calculation_service.get_vacation_account(db, employee, yr)["remaining_days"]
                    ))
                if not schedule.track_hours:
                    remaining_by_year[yr] -= day_consumption
                elif remaining_by_year[yr] >= day_consumption:
                    day_type = AbsenceType.VACATION
                    remaining_by_year[yr] -= day_consumption
                else:
                    day_type = AbsenceType.OVERTIME

            absence = Absence(
                user_id=employee.id,
                tenant_id=current_user.tenant_id,
                date=workday,
                # #394 Teil B: jede generierte Absence ist ein EINZELTAG. Vorher
                # trug jeder Tag end_date=closure.end_date -> die Abwesenheitsliste
                # zeigte je Zeile die ganze Closure-Spanne (z. B. "24.12 - 31.12"),
                # der Schichtplaner las sie als Mehrtages-Span. Die Zugehoerigkeit
                # zur Schließung steckt in note ("Betriebsferien: ...") + closure_id.
                end_date=None,
                type=day_type,
                hours=float(booked_target),
                # #205-Konsistenz (Review 2026-06-23): Betriebsferien decken den
                # GANZEN (Arbeits-)Tag ab -> half_day=False (voller Absenz-Tag),
                # damit get_vacation_account den tagebasierten (WHChange-stabilen)
                # Pfad nimmt und das Tagessoll voll auf 0 setzt (kein Rest-Defizit).
                # #394: an einem `half_day`-Sondertag (24./31.12.) ist der Tag nur
                # ein halber Arbeitstag -> hours=0,5×Soll (oben) + Urlaubs-/Absenz-
                # KOSTEN 0,5 kommen ueber den Sondertags-Faktor in get_vacation_
                # account/absence_days, NICHT ueber half_day (das wuerde das Soll
                # doppelt halbieren -> Phantom-Defizit).
                half_day=False,
                note=f"Betriebsferien: {closure.name}",
                closure_id=closure.id,
            )
            db.add(absence)
            # Innerhalb DIESES Aufrufs gebuchte Tage sofort mitzaehlen. `existing_keys`
            # stammt aus einer EINMALIGEN Vorab-Query; ohne diese Zeile sieht der
            # Duplikat-Check weiter unten die gerade angelegte, noch nicht geflushte
            # Abwesenheit nicht — bei ueberlappenden Betriebsferien entstuenden zwei
            # VACATION-Zeilen auf demselben Tag und der Insert-Batch scheiterte am
            # uq_tenant_user_date_type-Constraint (HTTP 500).
            existing_keys.add((employee.id, workday))
            created_for_employee = True
        if created_for_employee:
            affected += 1
    return affected


# Teil B: Summen-Audit beim automatischen Neubuchen (Sondertag / verkürzter Tag).
CLOSURE_REBOOK_REASON = "Sondertag oder verkürzter Tag geändert, wird neu gebucht"


def closure_years(db: Session, tenant_id) -> Set[int]:
    """Alle Jahre, die eine Schließung des Mandanten berührt (F-026)."""
    years: Set[int] = set()
    for start, end in db.query(CompanyClosure.start_date, CompanyClosure.end_date).filter(
        CompanyClosure.tenant_id == tenant_id,  # F-026
    ).all():
        years.update(range(start.year, end.year + 1))
    return years


def resave_closures_for_dates(
    db: Session, current_user: User, dates: Set[date], closed_years=None,
) -> None:
    """Teil B: Betriebsferien-Buchungen an ``dates`` neu buchen, nachdem sich
    deren Sondertag-/Verkürzt-Zustand geändert hat (Soll, Verbrauch, ``free``).

    Folgt ``closure_split_service.rebook_freed_closure_days``, nicht
    ``update_closure``: nur die betroffenen Tage, in der Transaktion des
    Aufrufers (committet nie). Der Aufrufer hat den neuen Zustand bereits
    geflusht, damit ``get_special_day_config`` ihn sieht.

    - Tage in abgeschlossenen Jahren bleiben unangetastet (Fix #5: dort nur
      Warnung, die der Aufrufer über ``stale_year_closing_warning`` liefert).
    - Gelöscht und neu gebucht werden nur Zeilen aktiver Teilnehmender an Tagen
      ohne Zeiteintrag (#290); Zeilen Ausgeschiedener/Abgewählter und
      gearbeitete Tage bleiben stehen.
    - Sperren: Anker auf Teilnehmende ∪ Zeilen-Eigentümer ∪ Admin EINMAL vor
      der ersten Löschung (``_lock_participant_rows``: erst sperren, dann
      schreiben). Die Zeile des verkürzten Tags, die der Aufrufer vorher
      schreibt, nimmt über ``created_by`` nur ein ``FOR KEY SHARE`` auf die
      Admin-Zeile — verträglich mit dem ``FOR NO KEY UPDATE``-Anker.
    - Zustand erst NACH der Sperre lesen (#491 API-2): die Vorab-Abfrage
      bestimmt nur die Sperrmenge; Teilnehmende und verknüpfte Zeilen werden
      danach neu gelesen und auf die gesperrte Menge beschränkt (wer erst
      danach Teilnehmer wird, bucht über seinen eigenen Pfad —
      ``_enroll_user_in_open_closures``).

    Keine Rückgabe: abgeschlossene Jahre sind oben ausgenommen, hier ändert
    sich dort nie eine Buchung — die Jahresabschluss-Warnung liefert allein der
    Aufrufer (``stale_year_closing_warning`` / ``closed_year_warning_text``).
    """
    tid = current_user.tenant_id
    # ``closed_years``: vom Aufrufer bereits ermittelt (spart die zweite Abfrage).
    closed = set(
        closed_years if closed_years is not None
        else calculation_service.all_closed_years(db, tid)
    )
    remaining = {d for d in (dates or ()) if d.year not in closed}
    if not remaining:
        return

    lo, hi = min(remaining), max(remaining)
    closures = [
        c for c in db.query(CompanyClosure).filter(
            CompanyClosure.tenant_id == tid,  # F-026
            CompanyClosure.start_date <= hi,
            CompanyClosure.end_date >= lo,
        ).order_by(CompanyClosure.start_date).all()
        if any(c.start_date <= d <= c.end_date for d in remaining)
    ]
    if not closures:
        return

    closure_ids = [c.id for c in closures]

    def _participants():
        # Teilnehmermenge wie update_closure (#189).
        return db.query(User).filter(
            User.is_active == True,
            User.receives_company_closures == True,
            User.tenant_id == tid,  # F-026
        ).all()

    def _linked():
        return db.query(Absence).filter(
            Absence.tenant_id == tid,  # F-026
            Absence.closure_id.in_(closure_ids),
            Absence.date.in_(remaining),
        ).all()

    # Vorab-Lesen NUR für die Sperrmenge (ungesperrt).
    locked_ids = (
        {e.id for e in _participants()}
        | {a.user_id for a in _linked()}
        | {current_user.id}
    )
    _lock_participant_rows(db, tid, locked_ids)
    # Zustand erst nach der Sperre lesen; nur gesperrte Personen anfassen.
    participants = [e for e in _participants() if e.id in locked_ids]
    participant_ids = {e.id for e in participants}
    linked = [a for a in _linked() if a.user_id in locked_ids]

    # #290: gearbeitete Tage bleiben, wie _worked_keys in update_closure.
    worked_keys = set()
    if participant_ids:
        worked_keys = {
            (uid, d) for uid, d in db.query(TimeEntry.user_id, TimeEntry.date).filter(
                TimeEntry.tenant_id == tid,  # F-026
                TimeEntry.user_id.in_(participant_ids),
                TimeEntry.date.in_(remaining),
            ).all()
        }

    linked_by_closure: dict = {}
    for a in linked:
        linked_by_closure.setdefault(a.closure_id, []).append(a)
    for closure in closures:
        deleted = 0
        for a in linked_by_closure.get(closure.id, []):
            if a.user_id in participant_ids and (a.user_id, a.date) not in worked_keys:
                db.delete(a)
                deleted += 1
        _audit_closure_absence_deletion(db, current_user, closure, deleted, CLOSURE_REBOOK_REASON)
    # Löschungen sichtbar machen, bevor der Create-Helper existing_keys liest.
    db.flush()

    split_needed = False
    for closure in closures:
        holidays = _get_holidays_for_range(db, closure.start_date, closure.end_date, tid)
        holidays |= special_days_service.free_special_days_in_range(
            db, tid, closure.start_date, closure.end_date
        )
        workdays = [
            d for d in _get_workdays(closure.start_date, closure.end_date, holidays)
            if d in remaining
        ]
        if workdays:
            _create_closure_absences(
                db, closure, workdays, participants, current_user, delete_time_entries=False
            )
            # Überlappende Schließungen müssen diese Buchung sehen.
            db.flush()
        if closure.counts_as_vacation:
            split_needed = True

    if split_needed and settings_service.get_bool_setting(
        db, "closure_overtime_after_vacation", tid, False
    ):
        db.flush()
        for yr in sorted({d.year for d in remaining}):
            _resplit_year_closures(db, tid, yr, current_user)

    db.flush()


@router.get("/", response_model=List[CompanyClosureResponse])
def list_closures(
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all company closures."""
    # F-026: tenant-scoped query (belt-and-suspenders on top of RLS).
    closures = db.query(CompanyClosure).filter(
        CompanyClosure.tenant_id == current_user.tenant_id,
    ).order_by(CompanyClosure.start_date.desc()).offset(skip).limit(limit).all()

    # affected_employees PRO Betriebsferien: die Zahl der MA, die tatsächlich eine
    # generierte Absence zu DIESER Schließung haben (eine MA, die an dem Tag schon
    # eine Fremd-Absence hatte, wurde übersprungen und zählt hier nicht mit). Eine
    # einzige GROUP-BY-Query statt einer Zählung pro Schließung (N+1).
    closure_ids = [c.id for c in closures]
    affected_by_closure: dict = {}
    if closure_ids:
        rows = (
            db.query(
                Absence.closure_id,
                func.count(func.distinct(Absence.user_id)),
            )
            .filter(
                Absence.closure_id.in_(closure_ids),
                Absence.tenant_id == current_user.tenant_id,
            )
            .group_by(Absence.closure_id)
            .all()
        )
        affected_by_closure = {cid: cnt for cid, cnt in rows}

    result = []
    for c in closures:
        result.append(CompanyClosureResponse(
            id=str(c.id),
            name=c.name,
            start_date=c.start_date,
            end_date=c.end_date,
            created_by=str(c.created_by),
            counts_as_vacation=c.counts_as_vacation,
            affected_employees=affected_by_closure.get(c.id, 0),
        ))
    return result


@router.post("/", response_model=CompanyClosureResponse, status_code=status.HTTP_201_CREATED)
def create_closure(
    data: CompanyClosureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Create a company closure (Betriebsferien).
    Automatically creates vacation absences for all active employees.
    """
    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="Enddatum darf nicht vor dem Startdatum liegen")
    # Release-Review 1.18.2: dieselbe Klemme wie im Urlaubsantrag
    # (``vacation_requests``, POST und PATCH). Betriebsferien sind der
    # destruktivere Pfad — sie loeschen beim Anlegen die Zeiteintraege ALLER
    # Teilnehmenden pro Werktag —, standen aber als einziger Spannen-Pfad ohne
    # Obergrenze da: ein Zahlendreher im Jahr (2036 statt 2026) haette in einem
    # Request die komplette rueckwirkende Zeiterfassung der Praxis geloescht.
    if (data.end_date - data.start_date).days > 366:
        raise HTTPException(status_code=400, detail="Der Zeitraum darf maximal ein Jahr umfassen")

    # Get all workdays in range
    holidays = _get_holidays_for_range(
        db, data.start_date, data.end_date, current_user.tenant_id
    )
    # AC-11: als 'free' konfigurierte Sondertage (24./31.12.) sind soll-frei und
    # dürfen keine Betriebsferien-Absence bekommen (sonst kostet ein freier Tag
    # fälschlich einen Urlaubstag) — wie Feiertage ausschließen.
    holidays |= special_days_service.free_special_days_in_range(
        db, current_user.tenant_id, data.start_date, data.end_date
    )
    workdays = _get_workdays(data.start_date, data.end_date, holidays)

    if not workdays:
        raise HTTPException(status_code=400, detail="Keine Arbeitstage im angegebenen Zeitraum")

    # #189: all active, participating employees of this tenant (F-026).
    # Participation is driven by the per-user receives_company_closures flag,
    # NOT by the role — an admin who also tracks time (e.g. a leitender
    # Angestellter with personnel-admin rights) must still get the closure.
    employees = db.query(User).filter(
        User.is_active == True,
        User.receives_company_closures == True,
        User.tenant_id == current_user.tenant_id,
    ).all()

    # Abschluss-Review 2026-07-31: Anker-Sperre VOR dem ersten Schreibzugriff.
    # Der INSERT der Schließungszeile nimmt über ``created_by`` ein
    # ``FOR KEY SHARE`` auf der Zeile des handelnden Admins; stand er vor dem
    # Anker, eskalierte diese Transaktion unmittelbar danach auf ``FOR UPDATE``
    # derselben Zeile (der Admin ist über ``receives_company_closures`` per
    # Voreinstellung selbst Teilnehmer) — die Reihenfolge-Umkehr, aus der zwei
    # gleichzeitige Vorgänge ein ``deadlock detected`` (HTTP 500) machten.
    # Reihenfolge jetzt identisch zu ``update_closure``. Die Zeile des Admins
    # gehört auch dann in die Menge, wenn er NICHT teilnimmt — ``created_by``
    # referenziert sie trotzdem.
    _lock_participant_rows(
        db, current_user.tenant_id,
        [e.id for e in employees] + [current_user.id],
    )

    # Create closure record (erst JETZT — nach der Anker-Sperre).
    closure = CompanyClosure(
        name=data.name,
        start_date=data.start_date,
        end_date=data.end_date,
        counts_as_vacation=data.counts_as_vacation,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    db.add(closure)
    db.flush()  # Get ID without commit

    affected = _create_closure_absences(db, closure, workdays, employees, current_user)

    # #314 follow-up: re-classify ALL of the year's vacation-closure absences in
    # CALENDAR order so the budget is consumed earliest-first across closures
    # (surplus → OVERTIME on the LAST closure), independent of the order the
    # closures were entered. Only for a vacation closure with the toggle on.
    if data.counts_as_vacation and settings_service.get_bool_setting(
        db, "closure_overtime_after_vacation", current_user.tenant_id, False
    ):
        db.flush()  # make the freshly created absences visible to the re-split queries
        for yr in range(data.start_date.year, data.end_date.year + 1):
            _resplit_year_closures(db, current_user.tenant_id, yr, current_user)

    # Gesamtreview 1.20 B5 (Nachzug): eine nachgetragene Schließung in einem
    # Jahr mit Jahresabschluss bucht dort Urlaub — Warnung wie beim Löschen.
    db.flush()
    warning = _closed_year_warning_for_changes(
        db, current_user.tenant_id, set(),
        _closure_booking_state(db, closure.id, current_user.tenant_id),
    )

    db.commit()
    db.refresh(closure)

    return CompanyClosureResponse(
        id=str(closure.id),
        name=closure.name,
        start_date=closure.start_date,
        end_date=closure.end_date,
        created_by=str(closure.created_by),
        counts_as_vacation=closure.counts_as_vacation,
        # #298: count only employees who actually received an absence. With the
        # employment-window guard, future-start / departed employees (and anyone
        # with a pre-existing foreign absence) are skipped — so len(employees)
        # would over-count. _create_closure_absences returns the distinct count
        # of employees that got ≥1 absence, matching list_closures' COUNT(DISTINCT).
        affected_employees=affected,
        warning=warning,
    )


@router.put("/{closure_id}", response_model=CompanyClosureResponse)
def update_closure(
    closure_id: str,
    data: CompanyClosureUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update a company closure (name + date range) and re-synchronise the
    generated absences.

    - Newly covered workdays get fresh absences (VACATION or PAID_LEAVE per
      ``counts_as_vacation``, with the same skip-logic that never overwrites
      a foreign absence).
    - Absences for days no longer in range are removed (matched via
      ``closure_id`` FK, not the note string).
    - Absences of tracked participants on days without a daily target are
      removed (legacy 0-h rows from before Gesamtreview 1.20 B5 — the create
      helper no longer books such days).
    - On rename, the ``note`` of all still-linked absences is updated.
    - On a Urlaub<->Freistellung switch, the ``type`` of all still-linked
      absences is updated to match the new flag (#145).
    - If the bookings change in a year whose Jahresabschluss already exists,
      the response carries ``warning`` (stale carryover, like delete_closure).
    """
    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="Enddatum darf nicht vor dem Startdatum liegen")
    # Release-Review 1.18.2: dieselbe Klemme wie im Urlaubsantrag
    # (``vacation_requests``, POST und PATCH). Betriebsferien sind der
    # destruktivere Pfad — sie loeschen beim Anlegen die Zeiteintraege ALLER
    # Teilnehmenden pro Werktag —, standen aber als einziger Spannen-Pfad ohne
    # Obergrenze da: ein Zahlendreher im Jahr (2036 statt 2026) haette in einem
    # Request die komplette rueckwirkende Zeiterfassung der Praxis geloescht.
    if (data.end_date - data.start_date).days > 366:
        raise HTTPException(status_code=400, detail="Der Zeitraum darf maximal ein Jahr umfassen")

    # F-026: tenant-scoped lookup.
    closure = db.query(CompanyClosure).filter(
        CompanyClosure.id == closure_id,
        CompanyClosure.tenant_id == current_user.tenant_id,
    ).first()
    if not closure:
        raise HTTPException(status_code=404, detail="Betriebsferien nicht gefunden")

    name_changed = closure.name != data.name
    type_changed = closure.counts_as_vacation != data.counts_as_vacation

    # Apply the new attributes on the closure first so generated notes /
    # end_date / absence type use the updated values.
    closure.name = data.name
    closure.start_date = data.start_date
    closure.end_date = data.end_date
    closure.counts_as_vacation = data.counts_as_vacation

    # #145: the type the still-linked absences should carry after this PUT.
    new_absence_type = (
        AbsenceType.VACATION if data.counts_as_vacation else AbsenceType.PAID_LEAVE
    )

    # Target workdays of the (new) range.
    holidays = _get_holidays_for_range(
        db, data.start_date, data.end_date, current_user.tenant_id
    )
    # AC-11: als 'free' konfigurierte Sondertage (24./31.12.) sind soll-frei und
    # dürfen keine Betriebsferien-Absence bekommen (sonst kostet ein freier Tag
    # fälschlich einen Urlaubstag) — wie Feiertage ausschließen.
    holidays |= special_days_service.free_special_days_in_range(
        db, current_user.tenant_id, data.start_date, data.end_date
    )
    workdays = _get_workdays(data.start_date, data.end_date, holidays)

    if not workdays:
        raise HTTPException(status_code=400, detail="Keine Arbeitstage im angegebenen Zeitraum")

    workday_set = set(workdays)

    # #314 (+ follow-up, customer report): when the surplus-as-overtime split is
    # active for a vacation closure, ANY update — including a plain re-save or a
    # cosmetic rename — re-applies the split. We DELETE the linked in-range absences
    # and let _create_closure_absences re-book them against a FRESH budget snapshot.
    # The snapshot is computed WITHOUT this closure's own days (they are deleted +
    # flushed first), so re-splitting when nothing else changed is value-stable
    # (idempotent). This is the supported way to apply a *newly enabled* global
    # toggle to an EXISTING Betriebsferien: flipping the switch alone does not
    # re-book already-persisted absences — re-saving the closure does. Re-typing in
    # place would be unsafe (a counts_as_vacation toggle would blindly turn budget-
    # exhausted OVERTIME days back into VACATION and re-create minus-vacation).
    # Split off → legacy in-place sync.
    split_active = data.counts_as_vacation and settings_service.get_bool_setting(
        db, "closure_overtime_after_vacation", current_user.tenant_id, False
    )

    # All absences currently linked to this closure (tenant-scoped via FK).
    linked = db.query(Absence).filter(
        Absence.closure_id == closure.id,
        Absence.tenant_id == current_user.tenant_id,
    ).all()
    # Gesamtreview 1.20 B5 (Nachzug): Stand VOR dem Speichern, für die
    # Jahresabschluss-Warnung unten (gleiche Form wie _closure_booking_state).
    _bookings_before = {(a.user_id, a.date, a.type, float(a.hours)) for a in linked}

    # Remove absences for days that are no longer covered by the closure;
    # keep the rest in sync (note on rename, single-day end_date reset per #394,
    # type on Urlaub<->Freistellung switch, #145). Each covered day holds at
    # most one closure-absence (the create helper skips days with an existing
    # absence), so flipping its type can never collide with the
    # (tenant_id, user_id, date, type) unique constraint.
    # Release-Review 1.16.0: Wen der Create-Helper unten überhaupt wieder bucht,
    # muss VOR dem Löschen feststehen. Er bucht nur für aktive Teilnehmer — eine
    # ausgeschiedene (`is_active=False`) oder abgewählte
    # (`receives_company_closures=False`) Person bekam ihre Closure-Absencen also
    # gelöscht und nie zurück. Das traf ausgerechnet den in CLAUDE.md
    # dokumentierten Migrationsweg „Toggle nachträglich aktivieren → Schließung neu
    # speichern": ein reines Umbenennen genügte, um bei aktivem #314-Split den
    # genommenen Urlaub eines Ausgeschiedenen rückwirkend verschwinden zu lassen
    # (Urlaubskonto, Abgeltungsbasis, §16-Beleg — ohne jede Spur).
    employees = db.query(User).filter(
        User.is_active == True,
        User.receives_company_closures == True,
        User.tenant_id == current_user.tenant_id,
    ).all()
    _rebookable_user_ids = {e.id for e in employees}

    # Audit 2026-07-31 (A2): die Anker-Sperren HIER holen — vor den Löschungen
    # unten und damit vor jeder Absence-Sperre dieser Transaktion. Würde erst
    # ``_create_closure_absences`` sie holen, sperrte dieser Pfad in der
    # Reihenfolge Abwesenheit → Benutzer und liefe damit einem gleichzeitigen
    # ``create_absence`` (Benutzer → Abwesenheit) in ein ABBA-Deadlock.
    # Die zu löschenden Abwesenheiten können auch Ausgeschiedenen/Abgewählten
    # gehören, die nicht in ``employees`` stehen → beide Mengen vereinigen.
    # Abschluss-Review 2026-07-31: zusätzlich die Zeile des handelnden Admins —
    # die Summen-Audit-Zeile unten referenziert sie über
    # ``user_id``/``changed_by`` und nimmt darauf ein ``FOR KEY SHARE``.
    _lock_participant_rows(
        db, current_user.tenant_id,
        _rebookable_user_ids | {a.user_id for a in linked} | {current_user.id},
    )

    # Release-Review 1.18.2: Wen der Create-Helper wieder bucht, war oben geklärt
    # (Teilnehmermenge) — WELCHE TAGE er überspringt, nicht. Er lässt jeden Tag
    # aus, an dem bereits Arbeitszeit gebucht ist (#290, „Arbeit gewinnt", er läuft
    # hier mit delete_time_entries=False). Eine Abwesenheit auf so einem Tag wurde
    # also gelöscht und nie zurückgebucht, während die Audit-Zeile „werden neu
    # gebucht" behauptete: ein reines Umbenennen ließ bei aktivem #314-Split den
    # Urlaubstag ersatzlos verschwinden (Urlaubskonto zu hoch, Soll lebt wieder auf,
    # §16-Beleg lückenhaft). Solche Zeilen bleiben stehen und werden nur in-place
    # synchronisiert — wie die der Ausgeschiedenen/Abgewählten.
    _worked_keys = set()
    _linked_user_ids = {a.user_id for a in linked}
    if _linked_user_ids:
        _worked_keys = {
            (uid, d) for uid, d in db.query(TimeEntry.user_id, TimeEntry.date).filter(
                TimeEntry.tenant_id == current_user.tenant_id,  # F-026
                TimeEntry.user_id.in_(_linked_user_ids),
                TimeEntry.date >= data.start_date,
                TimeEntry.date <= data.end_date,
            ).all()
        }

    # Gesamtreview 1.20 B5 (Nachzug): Altbestand an Tagen ohne Tagessoll. Bis B5
    # buchte der Create-Helper im gleichmäßigen Modus auch an Tagen ohne
    # Tagessoll (0 Wochenstunden, z. B. Elternzeit) eine 0-h-„Urlaub"-Zeile;
    # steht der Vertrag HEUTE auf 0 h, zählt das Urlaubskonto jede davon als
    # ganzen Urlaubstag. Seit B5 bucht er dort nichts mehr — ein neues Speichern
    # räumt den Bestand der Teilnehmenden deshalb in BEIDEN Modi ab (bei aktivem
    # #314-Split liefen solche Zeilen bisher unter „werden neu gebucht" mit,
    # ohne neu gebucht zu werden; bei abgeschaltetem blieben sie stehen).
    # Bedingung = Skip des Create-Helpers (``is_vacation_billable_day``: mit
    # Stundenzählung und Tagessoll 0 laut Snapshot zum Datum, #431); ohne
    # Stundenzählung (#191) zählt jeder Schließtag und bleibt. Ausgeschiedene/
    # Abgewählte fasst dieses Speichern wie oben nicht an. Unabhängig von
    # ``_worked_keys``: die Zeile wird nicht neu gebucht, die Arbeitszeit bleibt.
    # Teil A: Stundenzählung je Abwesenheitsdatum — ``is_vacation_billable_day``
    # liest sie aus dem Snapshot (ohne Stundenzählung zählt jeder Schließtag).
    _participants_by_id = {e.id: e for e in employees}
    _participant_linked_ids = {
        a.user_id for a in linked if a.user_id in _participants_by_id
    }
    _zero_target_ids = set()
    if _participant_linked_ids:
        _wh_by_user = calculation_service.wh_changes_by_user(
            db, current_user.tenant_id, _participant_linked_ids)
        _zero_target_ids = {
            a.id for a in linked
            if a.user_id in _participant_linked_ids and a.date in workday_set
            and not calculation_service.is_vacation_billable_day(
                db, _participants_by_id[a.user_id], a.date,
                wh_changes=_wh_by_user.get(a.user_id, []),
            )
        }

    _deleted_out_of_range = 0
    _deleted_zero_target = 0
    _deleted_for_resplit = 0
    for absence in linked:
        if absence.date not in workday_set:
            db.delete(absence)
            _deleted_out_of_range += 1
        elif absence.id in _zero_target_ids:
            db.delete(absence)
            _deleted_zero_target += 1
        elif (split_active and absence.user_id in _rebookable_user_ids
                and (absence.user_id, absence.date) not in _worked_keys):
            # delete → re-created + re-split by the create helper below
            db.delete(absence)
            _deleted_for_resplit += 1
        else:
            if name_changed:
                absence.note = f"Betriebsferien: {data.name}"
            # #394 Teil B: Closure-Absencen sind Einzeltage (siehe _create_closure_
            # absences) — nie die ganze Spanne an jedem Datum.
            absence.end_date = None
            if type_changed:
                absence.type = new_absence_type

    _audit_closure_absence_deletion(
        db, current_user, closure, _deleted_out_of_range,
        "Tag nicht mehr vom Zeitraum abgedeckt",
    )
    _audit_closure_absence_deletion(
        db, current_user, closure, _deleted_zero_target,
        "Tag ohne Tagessoll (0 Stunden geplant), wird nicht neu gebucht",
    )
    _audit_closure_absence_deletion(
        db, current_user, closure, _deleted_for_resplit,
        "Neuaufteilung Urlaub/Überstundenausgleich (#314), werden neu gebucht",
    )

    # L-3: die obigen Deletes/Updates in die DB schreiben, BEVOR der Create-Helper
    # seine existing_keys-Vorabfrage stellt — sonst sähe er die behaltenen Tage
    # nicht, würde sie erneut einfügen und am (tenant_id, user_id, date, type)-
    # Unique-Constraint mit einem 500 scheitern.
    db.flush()

    # Add absences for newly covered workdays. Reuse the create-time helper,
    # which already skips days where the employee has ANY existing absence
    # (foreign absences stay untouched, and days we kept above are skipped).
    # (employees wurde oben geladen — der Löschzweig braucht die Menge bereits.)
    # #290: re-save must NOT delete logged work. delete_time_entries=False →
    # days where a participant already logged real time are left intact (no
    # closure-absence booked over them). New participants still get absences on
    # their non-worked covered days. Only the initial create_closure clears entries.
    _create_closure_absences(
        db, closure, workdays, employees, current_user, delete_time_entries=False
    )

    # #314 follow-up: re-split the whole year in CALENDAR order (see create_closure)
    # so editing/re-saving ONE closure re-classifies ALL closures of the year
    # correctly (surplus → OVERTIME on the latest one). ``split_active`` already
    # encodes "vacation closure AND toggle on".
    if split_active:
        db.flush()
        for yr in range(data.start_date.year, data.end_date.year + 1):
            _resplit_year_closures(db, current_user.tenant_id, yr, current_user)

    # Gesamtreview 1.20 B5 (Nachzug): hat dieses Speichern Buchungen in einem
    # Jahr mit Jahresabschluss geändert (0-h-Altbestand abgeräumt, Zeitraum
    # gekürzt/verlängert, Urlaub ↔ Freistellung, neue Teilnehmende), ist dessen
    # eingefrorener Übertrag veraltet — Warnung wie beim Löschen. Ein reines
    # Umbenennen ändert nichts und bleibt still.
    db.flush()
    warning = _closed_year_warning_for_changes(
        db, current_user.tenant_id, _bookings_before,
        _closure_booking_state(db, closure.id, current_user.tenant_id),
    )

    db.commit()
    db.refresh(closure)

    # #298: report the AUTHORITATIVE distinct count of employees actually affected
    # by this closure (same COUNT(DISTINCT) as list_closures). The helper's return
    # value is only the NEWLY booked employees, which on a re-save (no new days)
    # would be 0; len(employees) would over-count out-of-window/foreign-absence MA.
    affected = db.query(func.count(func.distinct(Absence.user_id))).filter(
        Absence.closure_id == closure.id,
        Absence.tenant_id == current_user.tenant_id,  # F-026
    ).scalar() or 0

    return CompanyClosureResponse(
        id=str(closure.id),
        name=closure.name,
        start_date=closure.start_date,
        end_date=closure.end_date,
        created_by=str(closure.created_by),
        counts_as_vacation=closure.counts_as_vacation,
        affected_employees=affected,
        warning=warning,
    )


@router.delete("/{closure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_closure(
    closure_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Delete a company closure and remove all associated vacation absences.
    Associated absences are matched via the ``closure_id`` FK, so a renamed
    closure still removes exactly its own generated entries.
    """
    # F-026: tenant-scoped lookup.
    closure = db.query(CompanyClosure).filter(
        CompanyClosure.id == closure_id,
        CompanyClosure.tenant_id == current_user.tenant_id,
    ).first()
    if not closure:
        raise HTTPException(status_code=404, detail="Betriebsferien nicht gefunden")

    # Fix #2: remember the affected years BEFORE deleting so we can re-split the
    # REMAINING closures of those years (#314). Deleting the calendar-earlier,
    # budget-filling closure frees vacation budget — the OVERTIME days of a later
    # closure of the same year must flip back to VACATION.
    affected_years = list(range(closure.start_date.year, closure.end_date.year + 1))

    # Abschluss-Review 2026-07-31: Anker-Sperre VOR dem ersten Schreibzugriff —
    # dieselbe Reihenfolge wie create_/update_closure. Der Löschpfad hatte als
    # einziger der drei Betriebsferien-Pfade gar keinen Anker: er löscht
    # Abwesenheiten (Sperren auf ``absences``), schreibt eine Audit-Zeile
    # (``FOR KEY SHARE`` auf der Zeile des Admins) und lässt ggf. den
    # #314-Re-Split weitere Abwesenheiten umschreiben. Gegenüber einem
    # gleichzeitigen ``create_closure`` (hält jetzt FOR UPDATE auf den
    # Benutzerzeilen und will danach an die Abwesenheiten) ergab das erneut ein
    # ABBA: Abwesenheit → Benutzer hier, Benutzer → Abwesenheit dort.
    # Menge wie in ``update_closure`` (aktive Teilnehmer ∪ betroffene MA),
    # zusätzlich die Zeile des handelnden Admins (Audit-Fremdschlüssel).
    _linked_user_ids = {
        row[0] for row in db.query(Absence.user_id).filter(
            Absence.closure_id == closure.id,
            Absence.tenant_id == current_user.tenant_id,
        ).distinct().all()
    }
    _participant_ids = {
        row[0] for row in db.query(User.id).filter(
            User.is_active == True,
            User.receives_company_closures == True,
            User.tenant_id == current_user.tenant_id,
        ).all()
    }
    _lock_participant_rows(
        db, current_user.tenant_id,
        _linked_user_ids | _participant_ids | {current_user.id},
    )

    # Delete the generated absences via FK (robust against renames / manual
    # note edits) — tenant_id filter kept as belt-and-suspenders (F-026).
    _to_delete = db.query(Absence).filter(
        Absence.closure_id == closure.id,
        Absence.tenant_id == current_user.tenant_id,
    ).count()
    _audit_closure_absence_deletion(
        db, current_user, closure, _to_delete, "Betriebsferien gelöscht",
    )
    db.query(Absence).filter(
        Absence.closure_id == closure.id,
        Absence.tenant_id == current_user.tenant_id,
    ).delete(synchronize_session=False)

    db.delete(closure)

    # Fix #2: re-classify the remaining closures of the affected years in calendar
    # order (only when the global toggle is on; otherwise legacy all-VACATION).
    # Flush the deletes first so the budget snapshot no longer counts this
    # closure's own days.
    if settings_service.get_bool_setting(
        db, "closure_overtime_after_vacation", current_user.tenant_id, False
    ):
        db.flush()
        for yr in affected_years:
            _resplit_year_closures(db, current_user.tenant_id, yr, current_user)

    db.commit()

    # Fix #5: warn (non-destructively) if a deleted closure touched an already-
    # closed year — that year's frozen carryover is now stale.
    warning = calculation_service.stale_year_closing_warning(
        db, current_user.tenant_id, affected_years
    )
    if warning:
        return JSONResponse(status_code=200, content={"warning": warning})
    return None
