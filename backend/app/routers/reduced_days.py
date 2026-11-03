"""Teil B: Admin-Verwaltung verkürzter Tage (``/api/admin/reduced-days``).

Ein verkürzter Tag deckelt das Tagessoll auf ``max_hours``. Jede Änderung, die
den Zustand eines Datums ändert, bucht die Betriebsferien an diesem Datum in
derselben Transaktion neu (``company_closures.resave_closures_for_dates``);
abgeschlossene Jahre werden nur gemeldet (Fix #5).
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import require_admin
from app.models import ReducedDay, User
from app.routers import company_closures
from app.schemas.reduced_day import ReducedDayCreate, ReducedDayResponse, ReducedDayUpdate
from app.services import calculation_service, special_days_service
from app.services.work_window_service import join_warnings

router = APIRouter(
    prefix="/api/admin/reduced-days",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

SPECIAL_DAY_DATE_DETAIL = "Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden."
DUPLICATE_DETAIL = "Für dieses Datum ist bereits ein verkürzter Tag eingetragen."
NOT_FOUND_DETAIL = "Verkürzter Tag nicht gefunden"


def _to_response(row: ReducedDay, warning: Optional[str] = None) -> ReducedDayResponse:
    return ReducedDayResponse(
        id=str(row.id),
        date=row.date,
        label=row.label,
        max_hours=float(row.max_hours),
        created_at=row.created_at,
        warning=warning,
    )


def _reject_special_day_date(d: date) -> None:
    if (d.month, d.day) in ((12, 24), (12, 31)):
        raise HTTPException(status_code=400, detail=SPECIAL_DAY_DATE_DETAIL)


def _date_taken(db: Session, tenant_id, d: date, exclude_id=None) -> bool:
    q = db.query(ReducedDay.id).filter(
        ReducedDay.tenant_id == tenant_id,  # F-026
        ReducedDay.date == d,
    )
    if exclude_id is not None:
        q = q.filter(ReducedDay.id != exclude_id)
    return q.first() is not None


def _get_in_tenant(db: Session, rid: str, tenant_id) -> ReducedDay:
    row = db.query(ReducedDay).filter(
        ReducedDay.id == rid,
        ReducedDay.tenant_id == tenant_id,  # F-026
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)
    return row


def _flush_or_409(db: Session) -> None:
    """UNIQUE ``uq_reduced_days_tenant_date`` (Rennen nach der Vorabprüfung)
    → Rollback und 409; die Session wird danach nicht weiter benutzt."""
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_DETAIL)


def _apply_change(db: Session, current_user: User, before: dict, after: dict) -> Optional[str]:
    """Warnung + Neubuchung der Betriebsferien für die geänderten Tage.
    Der Aufrufer hat den neuen Stand geflusht und committet danach einmal."""
    tid = current_user.tenant_id
    changed = special_days_service.changed_dates(before, after)
    return join_warnings(
        calculation_service.stale_year_closing_warning(
            db, tid, special_days_service.years_affected_by_change(db, tid, before, after)
        ),
        company_closures.resave_closures_for_dates(db, current_user, changed),
    )


@router.get("/", response_model=List[ReducedDayResponse])
def list_reduced_days(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    q = db.query(ReducedDay).filter(ReducedDay.tenant_id == current_user.tenant_id)  # F-026
    if year is not None:
        q = q.filter(ReducedDay.date >= date(year, 1, 1), ReducedDay.date <= date(year, 12, 31))
    return [_to_response(r) for r in q.order_by(ReducedDay.date).all()]


@router.post("/", response_model=ReducedDayResponse, status_code=status.HTTP_201_CREATED)
def create_reduced_day(
    body: ReducedDayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    _reject_special_day_date(body.date)
    tid = current_user.tenant_id
    if _date_taken(db, tid, body.date):
        raise HTTPException(status_code=409, detail=DUPLICATE_DETAIL)

    row = ReducedDay(
        tenant_id=tid,
        date=body.date,
        label=body.label,
        max_hours=body.max_hours,
        created_by=current_user.id,
    )
    db.add(row)
    _flush_or_409(db)  # get_special_day_config muss die Zeile sehen

    warning = _apply_change(
        db, current_user, {},
        special_days_service.reduced_day_states([(body.date, body.max_hours)]),
    )
    db.commit()
    db.refresh(row)
    return _to_response(row, warning)


@router.put("/{reduced_day_id}", response_model=ReducedDayResponse)
def update_reduced_day(
    reduced_day_id: str,
    body: ReducedDayUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tid = current_user.tenant_id
    row = _get_in_tenant(db, reduced_day_id, tid)
    _reject_special_day_date(body.date)
    if _date_taken(db, tid, body.date, exclude_id=row.id):
        raise HTTPException(status_code=409, detail=DUPLICATE_DETAIL)

    before = special_days_service.reduced_day_states([(row.date, row.max_hours)])
    row.date = body.date
    row.label = body.label
    row.max_hours = body.max_hours
    _flush_or_409(db)

    warning = _apply_change(
        db, current_user, before,
        special_days_service.reduced_day_states([(body.date, body.max_hours)]),
    )
    db.commit()
    db.refresh(row)
    return _to_response(row, warning)


@router.delete("/{reduced_day_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reduced_day(
    reduced_day_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = _get_in_tenant(db, reduced_day_id, current_user.tenant_id)
    before = special_days_service.reduced_day_states([(row.date, row.max_hours)])
    db.delete(row)
    db.flush()

    warning = _apply_change(db, current_user, before, {})
    db.commit()
    # Fix #5: wie holidays.delete_holiday — abgeschlossenes Jahr → 200 + {"warning"}.
    if warning:
        return JSONResponse(status_code=200, content={"warning": warning})
    return None
