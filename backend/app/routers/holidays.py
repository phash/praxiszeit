from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.services.timezone_service import today_local
from app.models import User
from app.models.public_holiday import PublicHoliday
from app.schemas.holiday import HolidayCreate, HolidayUpdate, HolidayResponse
from app.services import holiday_service

router = APIRouter(prefix="/api/holidays", tags=["holidays"])


def _get_custom_holiday_in_tenant(db: Session, holiday_id: str, current_user: User) -> PublicHoliday:
    """Look up a holiday by id, scoped to the caller's tenant (F-026).

    Raises 404 on not-found / cross-tenant access, 403 when the holiday is a
    workalendar-seeded standard holiday (only custom holidays may be edited or
    deleted — REQ-2).
    """
    holiday = (
        db.query(PublicHoliday)
        .filter(
            PublicHoliday.id == holiday_id,
            PublicHoliday.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not holiday:
        raise HTTPException(status_code=404, detail="Feiertag nicht gefunden")
    if not holiday.is_custom:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gesetzliche Feiertage können nicht bearbeitet oder gelöscht werden.",
        )
    return holiday


@router.get("/", response_model=List[HolidayResponse])
def list_holidays(
    year: int = Query(None, description="Year (default: current year)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List public holidays for a specific year (standard + custom).
    Available to all authenticated users.
    """
    year = year or today_local().year

    holidays = holiday_service.get_holidays(db, year, tenant_id=current_user.tenant_id)

    return holidays


@router.post("/", response_model=HolidayResponse, status_code=status.HTTP_201_CREATED)
def create_holiday(
    body: HolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a custom (admin-managed) holiday (admin only).

    Tenant-scoped; ``year`` is derived from the date. Rejects a duplicate
    (same tenant + date) regardless of provenance.
    """
    # Duplicate check: same tenant + date (F-026 explicit tenant filter)
    existing = (
        db.query(PublicHoliday)
        .filter(
            PublicHoliday.tenant_id == current_user.tenant_id,
            PublicHoliday.date == body.date,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An diesem Datum existiert bereits ein Feiertag.",
        )

    holiday = PublicHoliday(
        tenant_id=current_user.tenant_id,
        date=body.date,
        name=body.name,
        year=body.date.year,
        is_custom=True,
        source="admin",
    )
    db.add(holiday)
    db.commit()
    db.refresh(holiday)

    # F-034: invalidate the per-(tenant, year) holiday cache after the write.
    holiday_service.invalidate_holiday_cache(tenant_id=current_user.tenant_id, year=holiday.year)

    return holiday


@router.put("/{holiday_id}", response_model=HolidayResponse)
def update_holiday(
    holiday_id: str,
    body: HolidayUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Edit a custom holiday (admin only). Standard holidays return 403."""
    holiday = _get_custom_holiday_in_tenant(db, holiday_id, current_user)

    old_year = holiday.year

    if body.name is not None:
        holiday.name = body.name
    if body.date is not None and body.date != holiday.date:
        # Duplicate check when moving to a new date (same tenant + date).
        clash = (
            db.query(PublicHoliday)
            .filter(
                PublicHoliday.tenant_id == current_user.tenant_id,
                PublicHoliday.date == body.date,
                PublicHoliday.id != holiday.id,
            )
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An diesem Datum existiert bereits ein Feiertag.",
            )
        holiday.date = body.date
        holiday.year = body.date.year

    db.commit()
    db.refresh(holiday)

    # F-034: a date change can move the holiday between years -> invalidate both.
    holiday_service.invalidate_holiday_cache(tenant_id=current_user.tenant_id, year=old_year)
    holiday_service.invalidate_holiday_cache(tenant_id=current_user.tenant_id, year=holiday.year)

    return holiday


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(
    holiday_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a custom holiday (admin only). Standard holidays return 403."""
    holiday = _get_custom_holiday_in_tenant(db, holiday_id, current_user)
    year = holiday.year

    db.delete(holiday)
    db.commit()

    # F-034: invalidate the per-(tenant, year) holiday cache after the delete.
    holiday_service.invalidate_holiday_cache(tenant_id=current_user.tenant_id, year=year)

    return None


@router.get("/states")
def list_states(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List supported German federal states for holiday configuration."""
    return {
        "states": holiday_service.get_supported_states(),
        "current_state": holiday_service.get_holiday_state(db, tenant_id=current_user.tenant_id),
    }
