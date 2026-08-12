from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
from datetime import date, timedelta
from decimal import Decimal
from pydantic import BaseModel, ConfigDict

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
    name: str
    start_date: date
    end_date: date
    # #145: True (default) -> generated absences are VACATION (deduct the
    # vacation budget, legacy behaviour). False -> PAID_LEAVE (paid leave,
    # like a holiday: reduces target, no vacation deduction, balance-neutral).
    counts_as_vacation: bool = True


class CompanyClosureUpdate(BaseModel):
    name: str
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

    # #394: half-day special days (24./31.12. configured as "halber Feiertag")
    # have a 0.5 target factor. The closure must book only HALF a day for them —
    # otherwise a full vacation/overtime day is deducted for a 0.5-Soll day
    # (customer report philvdb). `free` special days already reduce the target to
    # 0 and are excluded from `workdays` upstream; only `half_day` reaches here.
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
        for wh in db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id.in_(emp_ids),
            WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        ).order_by(WorkingHoursChange.effective_from).all():
            wh_by_user.setdefault(wh.user_id, []).append(wh)

    for employee in employees:
        created_for_employee = False
        emp_wh = wh_by_user.get(employee.id, [])
        # #314: remaining vacation budget snapshot per year, consumed as we book
        # VACATION days; once exhausted the surplus days become OVERTIME.
        remaining_by_year: dict = {}
        # The split only makes sense for time-tracked employees: an untracked MA
        # (track_hours=False, daily target 0) has no overtime account, so an
        # OVERTIME day would vanish from all accounting. Keep legacy VACATION for
        # them (review finding).
        emp_split = split_overtime and employee.track_hours
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
            # Deckungsgleich mit ``calculation_service.is_vacation_billable_day``.
            if (employee.track_hours and schedule.use_daily_schedule
                    and day_target <= 0):
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

            # #394: a `half_day` special day (24./31.12.) contributes only 0.5×
            # its target — book a HALF day (half the target hours, half_day flag,
            # 0.5 budget consumption) instead of a full one.
            sd_factor = special_days_service.special_day_target_factor(
                workday, special_cfg_by_year[workday.year]
            )
            if sd_factor is not None and sd_factor == Decimal("0"):
                continue  # `free` day — defensive; already excluded from workdays
            is_half_special = sd_factor is not None and sd_factor == Decimal("0.5")
            booked_target = day_target * Decimal("0.5") if is_half_special else day_target
            day_consumption = 0.5 if is_half_special else 1.0

            # #314: decide VACATION vs OVERTIME per day. VACATION while the
            # remaining budget covers this day's consumption; afterwards OVERTIME
            # (no minus-vacation). Only positive-target days consume the snapshot.
            day_type = absence_type
            if emp_split and day_target > 0:
                yr = workday.year
                if yr not in remaining_by_year:
                    # Resturlaub des Jahres als TAGE-Budget (Tagesprinzip). Die
                    # closure-eigenen Tage sind beim Re-Save vorher gelöscht+geflusht
                    # bzw. beim Create noch nicht vorhanden → der Snapshot zählt sie
                    # nicht doppelt. So zehrt die Closure den VERBLEIBENDEN Urlaub
                    # chronologisch bis 0 auf, der Rest wird Überstundenausgleich —
                    # NIE Minus-Urlaub, auch wenn SPÄTER im Jahr Urlaub (z. B. Sommer)
                    # gebucht ist (der zählt korrekt mit; #314 Folgefix-Review).
                    remaining_by_year[yr] = float(
                        calculation_service.get_vacation_account(db, employee, yr)["remaining_days"]
                    )
                if remaining_by_year[yr] >= day_consumption:
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
    - On rename, the ``note`` of all still-linked absences is updated.
    - On a Urlaub<->Freistellung switch, the ``type`` of all still-linked
      absences is updated to match the new flag (#145).
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

    _deleted_out_of_range = 0
    _deleted_for_resplit = 0
    for absence in linked:
        if absence.date not in workday_set:
            db.delete(absence)
            _deleted_out_of_range += 1
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
