from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
from datetime import date, timedelta
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, Absence, AbsenceType, PublicHoliday, CompanyClosure, TimeEntry, WorkingHoursChange
from app.schemas.absence import AbsenceResponse
from app.services import calculation_service, settings_service, special_days_service
from app.routers.admin_helpers import _create_audit_log

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

    # #204: Statt ~3 Queries pro (MA × Arbeitstag) — bei z. B. 40 MA × 15 Tagen
    # ~1.800 SELECTs — die Referenzdaten in je EINER Query vorladen und in-memory
    # nachschlagen. Logik unveraendert.
    emp_ids = [e.id for e in employees]
    existing_keys = set()
    te_by_key: dict = {}
    wh_by_user: dict = {}
    if emp_ids:
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

            # F-027/#204: authoritative weekly_hours lookup (get_daily_target_for_date
            # must never fall back to user.weekly_hours; wh_changes vorgeladen).
            weekly_hours = calculation_service.get_weekly_hours_for_date(
                db, employee, workday, wh_changes=emp_wh
            )
            day_target = calculation_service.get_daily_target_for_date(
                employee, workday, weekly_hours=weekly_hours
            )
            # #314 (philvdb): an einem Nicht-Arbeitstag eines use_daily_schedule-
            # Teilzeitlers (Tagessoll 0 an diesem Wochentag) gibt es nichts zu
            # schließen — KEINE Buchung (sonst eine irreführende 0h-„Urlaub"-Zeile).
            # Vor der TimeEntry-Löschung, damit an einem solchen Tag nichts angefasst
            # wird. Untracked/leitende (track_hours=False → Tagessoll immer 0) NICHT
            # skippen: die bekommen tagebasiert 1 Urlaubstag pro Closure-Tag (#191).
            if (employee.track_hours and getattr(employee, "use_daily_schedule", False)
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

            # #314: decide VACATION vs OVERTIME per day. VACATION while the
            # remaining budget covers a full day; afterwards OVERTIME (no minus-
            # vacation). Only positive-target days consume the budget snapshot.
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
                if remaining_by_year[yr] >= 1.0:
                    day_type = AbsenceType.VACATION
                    remaining_by_year[yr] -= 1.0
                else:
                    day_type = AbsenceType.OVERTIME

            absence = Absence(
                user_id=employee.id,
                tenant_id=current_user.tenant_id,
                date=workday,
                end_date=closure.end_date,
                type=day_type,
                hours=float(day_target),
                # #205-Konsistenz (Review 2026-06-23): Betriebsferien sind immer
                # volle Tage -> half_day=False, damit get_vacation_account den
                # tagebasierten (WHChange-stabilen) Pfad nimmt statt der Legacy-
                # Stundenlogik (die bei spaeterer Stundenaenderung driften wuerde).
                half_day=False,
                note=f"Betriebsferien: {closure.name}",
                closure_id=closure.id,
            )
            db.add(absence)
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

    # Create closure record
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

    affected = _create_closure_absences(db, closure, workdays, employees, current_user)

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
    # keep the rest in sync (note on rename, end_date on range change,
    # type on Urlaub<->Freistellung switch, #145). Each covered day holds at
    # most one closure-absence (the create helper skips days with an existing
    # absence), so flipping its type can never collide with the
    # (tenant_id, user_id, date, type) unique constraint.
    for absence in linked:
        if absence.date not in workday_set:
            db.delete(absence)
        elif split_active:
            # delete → re-created + re-split by the create helper below
            db.delete(absence)
        else:
            if name_changed:
                absence.note = f"Betriebsferien: {data.name}"
            absence.end_date = data.end_date
            if type_changed:
                absence.type = new_absence_type

    # L-3: die obigen Deletes/Updates in die DB schreiben, BEVOR der Create-Helper
    # seine existing_keys-Vorabfrage stellt — sonst sähe er die behaltenen Tage
    # nicht, würde sie erneut einfügen und am (tenant_id, user_id, date, type)-
    # Unique-Constraint mit einem 500 scheitern.
    db.flush()

    # Add absences for newly covered workdays. Reuse the create-time helper,
    # which already skips days where the employee has ANY existing absence
    # (foreign absences stay untouched, and days we kept above are skipped).
    employees = db.query(User).filter(
        User.is_active == True,
        User.receives_company_closures == True,
        User.tenant_id == current_user.tenant_id,
    ).all()
    # #290: re-save must NOT delete logged work. delete_time_entries=False →
    # days where a participant already logged real time are left intact (no
    # closure-absence booked over them). New participants still get absences on
    # their non-worked covered days. Only the initial create_closure clears entries.
    _create_closure_absences(
        db, closure, workdays, employees, current_user, delete_time_entries=False
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

    # Delete the generated absences via FK (robust against renames / manual
    # note edits) — tenant_id filter kept as belt-and-suspenders (F-026).
    db.query(Absence).filter(
        Absence.closure_id == closure.id,
        Absence.tenant_id == current_user.tenant_id,
    ).delete(synchronize_session=False)

    db.delete(closure)
    db.commit()
    return None
