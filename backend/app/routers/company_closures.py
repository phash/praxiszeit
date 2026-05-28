from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import date, timedelta
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, Absence, AbsenceType, PublicHoliday, CompanyClosure, UserRole, TimeEntry
from app.schemas.absence import AbsenceResponse
from app.services import calculation_service
from app.routers.admin_helpers import _create_audit_log

router = APIRouter(prefix="/api/company-closures", tags=["company-closures"])


class CompanyClosureCreate(BaseModel):
    name: str
    start_date: date
    end_date: date


class CompanyClosureUpdate(BaseModel):
    name: str
    start_date: date
    end_date: date


class CompanyClosureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    start_date: date
    end_date: date
    created_by: str
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
) -> int:
    """Create VACATION absences linked to ``closure`` for the given workdays.

    Mirrors the create-time logic: skips any day where the employee already
    has an absence (Fremd-Absence wird nicht überschrieben), deletes existing
    time entries on covered days (with audit log) and credits the
    per-day target via the authoritative weekly_hours lookup.

    Returns the number of distinct employees that received at least one new
    absence.
    """
    affected = 0
    for employee in employees:
        created_for_employee = False
        for workday in workdays:
            # Skip if any absence already exists for this day (not just vacation)
            existing = db.query(Absence).filter(
                Absence.user_id == employee.id,
                Absence.tenant_id == current_user.tenant_id,
                Absence.date == workday,
            ).first()
            if existing:
                continue

            # Delete existing time entries on this day with audit log
            te_entries = db.query(TimeEntry).filter(
                TimeEntry.user_id == employee.id,
                TimeEntry.tenant_id == current_user.tenant_id,
                TimeEntry.date == workday,
            ).all()
            for entry in te_entries:
                _create_audit_log(
                    db, entry.id, employee.id, current_user.id,
                    action="delete", old_entry=entry,
                    source="company_closure",
                    tenant_id=current_user.tenant_id,
                )
                db.delete(entry)

            # F-027: Use the authoritative weekly_hours lookup so that
            # a closure spanning a WorkingHoursChange credits the right
            # daily target. Passing weekly_hours explicitly is a CLAUDE.md
            # requirement — get_daily_target_for_date must never fall
            # back to user.weekly_hours.
            weekly_hours = calculation_service.get_weekly_hours_for_date(
                db, employee, workday
            )
            absence = Absence(
                user_id=employee.id,
                tenant_id=current_user.tenant_id,
                date=workday,
                end_date=closure.end_date,
                type=AbsenceType.VACATION,
                hours=float(
                    calculation_service.get_daily_target_for_date(
                        employee, workday, weekly_hours=weekly_hours
                    )
                ),
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all company closures."""
    # F-026: tenant-scoped query (belt-and-suspenders on top of RLS).
    closures = db.query(CompanyClosure).filter(
        CompanyClosure.tenant_id == current_user.tenant_id,
    ).order_by(CompanyClosure.start_date.desc()).all()
    result = []
    for c in closures:
        # Count affected (employees with vacation created for this closure)
        employees = db.query(User).filter(
            User.is_active == True,
            User.role != UserRole.ADMIN,
            User.tenant_id == current_user.tenant_id,
        ).all()
        affected = len(employees)  # all active employees are affected
        result.append(CompanyClosureResponse(
            id=str(c.id),
            name=c.name,
            start_date=c.start_date,
            end_date=c.end_date,
            created_by=str(c.created_by),
            affected_employees=affected
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
        raise HTTPException(status_code=400, detail="Enddatum muss nach dem Startdatum liegen")

    # Create closure record
    closure = CompanyClosure(
        name=data.name,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    db.add(closure)
    db.flush()  # Get ID without commit

    # Get all workdays in range
    holidays = _get_holidays_for_range(
        db, data.start_date, data.end_date, current_user.tenant_id
    )
    workdays = _get_workdays(data.start_date, data.end_date, holidays)

    if not workdays:
        raise HTTPException(status_code=400, detail="Keine Arbeitstage im angegebenen Zeitraum")

    # Get all active employees (non-admin) of this tenant (F-026)
    employees = db.query(User).filter(
        User.is_active == True,
        User.role != UserRole.ADMIN,
        User.tenant_id == current_user.tenant_id,
    ).all()

    _create_closure_absences(db, closure, workdays, employees, current_user)

    db.commit()
    db.refresh(closure)

    return CompanyClosureResponse(
        id=str(closure.id),
        name=closure.name,
        start_date=closure.start_date,
        end_date=closure.end_date,
        created_by=str(closure.created_by),
        # All active employees are considered affected by the closure
        # (kept consistent with list_closures' naive count).
        affected_employees=len(employees),
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

    - Newly covered workdays get fresh VACATION absences (with the same
      skip-logic that never overwrites a foreign absence).
    - Absences for days no longer in range are removed (matched via
      ``closure_id`` FK, not the note string).
    - On rename, the ``note`` of all still-linked absences is updated.
    """
    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="Enddatum muss nach dem Startdatum liegen")

    # F-026: tenant-scoped lookup.
    closure = db.query(CompanyClosure).filter(
        CompanyClosure.id == closure_id,
        CompanyClosure.tenant_id == current_user.tenant_id,
    ).first()
    if not closure:
        raise HTTPException(status_code=404, detail="Betriebsferien nicht gefunden")

    name_changed = closure.name != data.name

    # Apply the new attributes on the closure first so generated notes /
    # end_date use the updated values.
    closure.name = data.name
    closure.start_date = data.start_date
    closure.end_date = data.end_date

    # Target workdays of the (new) range.
    holidays = _get_holidays_for_range(
        db, data.start_date, data.end_date, current_user.tenant_id
    )
    workdays = _get_workdays(data.start_date, data.end_date, holidays)

    if not workdays:
        raise HTTPException(status_code=400, detail="Keine Arbeitstage im angegebenen Zeitraum")

    workday_set = set(workdays)

    # All absences currently linked to this closure (tenant-scoped via FK).
    linked = db.query(Absence).filter(
        Absence.closure_id == closure.id,
        Absence.tenant_id == current_user.tenant_id,
    ).all()

    # Remove absences for days that are no longer covered by the closure;
    # keep the rest in sync (note on rename, end_date on range change).
    for absence in linked:
        if absence.date not in workday_set:
            db.delete(absence)
        else:
            if name_changed:
                absence.note = f"Betriebsferien: {data.name}"
            absence.end_date = data.end_date

    # Add absences for newly covered workdays. Reuse the create-time helper,
    # which already skips days where the employee has ANY existing absence
    # (foreign absences stay untouched, and days we kept above are skipped).
    employees = db.query(User).filter(
        User.is_active == True,
        User.role != UserRole.ADMIN,
        User.tenant_id == current_user.tenant_id,
    ).all()
    _create_closure_absences(db, closure, workdays, employees, current_user)

    db.commit()
    db.refresh(closure)

    return CompanyClosureResponse(
        id=str(closure.id),
        name=closure.name,
        start_date=closure.start_date,
        end_date=closure.end_date,
        created_by=str(closure.created_by),
        affected_employees=len(employees),
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
