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


def _get_holidays_for_range(db: Session, start: date, end: date) -> set:
    years = set(range(start.year, end.year + 1))
    holidays = set()
    for year in years:
        year_holidays = db.query(PublicHoliday).filter(PublicHoliday.year == year).all()
        holidays.update([h.date for h in year_holidays])
    return holidays


@router.get("/", response_model=List[CompanyClosureResponse])
def list_closures(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all company closures."""
    closures = db.query(CompanyClosure).order_by(CompanyClosure.start_date.desc()).all()
    result = []
    for c in closures:
        # Count affected (employees with vacation created for this closure)
        employees = db.query(User).filter(User.is_active == True, User.role != UserRole.ADMIN).all()
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
    holidays = _get_holidays_for_range(db, data.start_date, data.end_date)
    workdays = _get_workdays(data.start_date, data.end_date, holidays)

    if not workdays:
        raise HTTPException(status_code=400, detail="Keine Arbeitstage im angegebenen Zeitraum")

    # Get all active employees (non-admin)
    employees = db.query(User).filter(
        User.is_active == True,
        User.role != UserRole.ADMIN,
    ).all()

    affected = 0
    for employee in employees:
        for workday in workdays:
            # Skip if any absence already exists for this day (not just vacation)
            existing = db.query(Absence).filter(
                Absence.user_id == employee.id,
                Absence.date == workday,
            ).first()
            if not existing:
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

                absence = Absence(
                    user_id=employee.id,
                    tenant_id=current_user.tenant_id,
                    date=workday,
                    end_date=data.end_date,
                    type=AbsenceType.VACATION,
                    hours=float(calculation_service.get_daily_target_for_date(employee, workday)),
                    note=f"Betriebsferien: {data.name}"
                )
                db.add(absence)
        affected += 1

    db.commit()
    db.refresh(closure)

    return CompanyClosureResponse(
        id=str(closure.id),
        name=closure.name,
        start_date=closure.start_date,
        end_date=closure.end_date,
        created_by=str(closure.created_by),
        affected_employees=affected
    )


@router.delete("/{closure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_closure(
    closure_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Delete a company closure and remove all associated vacation absences.
    Only removes vacation entries that have the closure name in notes.
    """
    closure = db.query(CompanyClosure).filter(CompanyClosure.id == closure_id).first()
    if not closure:
        raise HTTPException(status_code=404, detail="Betriebsferien nicht gefunden")

    # LIMITATION: Absences are matched by note string, not by FK to closure.
    # If the closure name was edited or an absence note was changed manually,
    # this deletion will miss those entries. A proper fix requires adding a
    # closure_id FK column on the Absence model (needs migration).
    note_pattern = f"Betriebsferien: {closure.name}"
    holidays = _get_holidays_for_range(db, closure.start_date, closure.end_date)
    workdays = _get_workdays(closure.start_date, closure.end_date, holidays)

    db.query(Absence).filter(
        Absence.date.in_(workdays),
        Absence.type == AbsenceType.VACATION,
        Absence.note == note_pattern
    ).delete(synchronize_session=False)

    db.delete(closure)
    db.commit()
    return None
