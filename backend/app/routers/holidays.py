from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.services.timezone_service import today_local
from app.models import User
from app.models.public_holiday import PublicHoliday
from app.schemas.holiday import HolidayCreate, HolidayUpdate, HolidayResponse, HolidayWriteResponse
from app.services import calculation_service, holiday_service, work_window_service

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
    year: int = Query(None, ge=2000, le=2100, description="Year (default: current year)"),
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


@router.post("/", response_model=HolidayWriteResponse, status_code=status.HTTP_201_CREATED)
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

    # Fix #5 (Gesamtreview 1.20, wie der Bundesland-Wechsel seit B9): ein
    # Feiertag setzt Soll und Gutschrift des Tages auf 0 — liegt er in einem
    # abgeschlossenen Jahr, ist dessen Übertrag veraltet. Nur melden.
    response = HolidayWriteResponse.model_validate(holiday)
    response.warning = work_window_service.join_warnings(
        calculation_service.stale_year_closing_warning(
            db, current_user.tenant_id, {holiday.year}
        ),
        # Gesamtreview 1.20: die Kappung bestehender Einträge des Tages bleibt
        # stehen (E35 gilt beim Schreiben) — betroffene Einträge nennen.
        work_window_service.stale_clamp_hint(db, current_user.tenant_id, {holiday.date}),
    )
    return response


@router.put("/{holiday_id}", response_model=HolidayWriteResponse)
def update_holiday(
    holiday_id: str,
    body: HolidayUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Edit a custom holiday (admin only). Standard holidays return 403."""
    holiday = _get_custom_holiday_in_tenant(db, holiday_id, current_user)

    old_year = holiday.year
    old_date = holiday.date
    date_changed = False

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
        date_changed = True

    db.commit()
    db.refresh(holiday)

    # F-034: a date change can move the holiday between years -> invalidate both.
    holiday_service.invalidate_holiday_cache(tenant_id=current_user.tenant_id, year=old_year)
    holiday_service.invalidate_holiday_cache(tenant_id=current_user.tenant_id, year=holiday.year)

    # Fix #5: nur ein Datumswechsel verschiebt Soll/Saldo — altes UND neues
    # Jahr prüfen. Ein reines Umbenennen bleibt still.
    response = HolidayWriteResponse.model_validate(holiday)
    if date_changed:
        response.warning = work_window_service.join_warnings(
            calculation_service.stale_year_closing_warning(
                db, current_user.tenant_id, {old_year, holiday.year}
            ),
            work_window_service.stale_clamp_hint(
                db, current_user.tenant_id, {old_date, holiday.date}
            ),
        )
    return response


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(
    holiday_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a custom holiday (admin only). Standard holidays return 403."""
    holiday = _get_custom_holiday_in_tenant(db, holiday_id, current_user)
    year = holiday.year
    day = holiday.date

    db.delete(holiday)
    db.commit()

    # F-034: invalidate the per-(tenant, year) holiday cache after the delete.
    holiday_service.invalidate_holiday_cache(tenant_id=current_user.tenant_id, year=year)

    # Fix #5: wie delete_closure — abgeschlossenes Jahr → 200 + {"warning"}.
    warning = work_window_service.join_warnings(
        calculation_service.stale_year_closing_warning(
            db, current_user.tenant_id, {year}
        ),
        work_window_service.stale_clamp_hint(db, current_user.tenant_id, {day}),
    )
    if warning:
        return JSONResponse(status_code=200, content={"warning": warning})
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
