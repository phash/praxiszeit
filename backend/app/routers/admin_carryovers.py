"""Admin sub-router: Year Carryovers + Year Closing."""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import User, YearCarryover
from app.middleware.auth import require_admin
from app.schemas.year_carryover import YearCarryoverCreate, YearCarryoverResponse
from app.services import calculation_service

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users/{user_id}/carryovers", response_model=List[YearCarryoverResponse])
def list_carryovers(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all year carryovers for a user."""
    # F-026: explicit tenant scoping
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user.tenant_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    carryovers = db.query(YearCarryover).filter(
        YearCarryover.user_id == user_id,
        YearCarryover.tenant_id == current_user.tenant_id,  # F-026
    ).order_by(YearCarryover.year.desc()).all()

    return carryovers


@router.put("/users/{user_id}/carryovers/{year}", response_model=YearCarryoverResponse)
def upsert_carryover(
    user_id: str,
    year: int,
    data: YearCarryoverCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create or update year carryover (overtime hours & vacation days from previous year)."""
    # F-026: explicit tenant scoping
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user.tenant_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail=f"Ungültiges Jahr: {year} (erlaubt 2000–2100)")

    carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user_id,
        YearCarryover.tenant_id == current_user.tenant_id,  # F-026
        YearCarryover.year == year,
    ).first()

    if carryover:
        carryover.overtime_hours = data.overtime_hours
        carryover.vacation_days = data.vacation_days
        # Fix #7: a manual edit takes ownership — protect it from
        # delete_year_closing (which removes only source='year_closing').
        carryover.source = "manual"
    else:
        carryover = YearCarryover(
            user_id=user_id,
            tenant_id=current_user.tenant_id,
            year=year,
            overtime_hours=data.overtime_hours,
            vacation_days=data.vacation_days,
            source="manual",  # Fix #7
        )
        db.add(carryover)

    db.commit()
    db.refresh(carryover)
    return carryover


@router.post("/year-closing/{year}")
def create_year_closing(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Create year-end closing: calculates overtime balance and remaining vacation
    for all active users at Dec 31 and creates carryover records for year+1.
    """
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail=f"Ungültiges Jahr: {year} (erlaubt 2000–2100)")

    # F-029: Serialize year-closing per (tenant, year). Two admins clicking
    # simultaneously would otherwise race on the upsert of YearCarryover and
    # also compute against a moving snapshot of time entries. pg_advisory_xact_lock
    # uses a namespaced 64-bit key (namespace=42, payload=hash(tenant,year))
    # and releases at transaction end regardless of commit/rollback.
    # SQLite ignores pg_advisory_xact_lock — only Postgres enforces this.
    from sqlalchemy import text
    try:
        lock_key = hash((str(current_user.tenant_id), year)) & 0x7FFFFFFFFFFFFFFF
        db.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :key)"),
            {"ns": 42, "key": lock_key},
        )
    except Exception:
        # Non-Postgres backends (tests on SQLite) don't have this function;
        # accept the loss of serialization since tests run single-threaded.
        pass

    # F-029: refuse the operation if any change request for the closing
    # year is still pending — approving it later would retroactively move
    # the balance we just froze.
    from app.models.change_request import ChangeRequest, ChangeRequestStatus
    start_of_year = date(year, 1, 1)
    end_of_year = date(year, 12, 31)

    def _in_closing_year(col):
        return and_(col >= start_of_year, col <= end_of_year)

    # Audit 2026-07-31 (A1): über BEIDE Datumsspalten prüfen, nicht nur
    # ``proposed_date``.
    #  * Ein LÖSCH-Antrag trägt in ``proposed_date`` NULL — sein Tagesbezug steht
    #    ausschließlich in ``original_date``. Er wurde bisher still nicht
    #    gezählt: der Jahresabschluss lief durch, und eine spätere Genehmigung
    #    löschte den Zeiteintrag, während der eingefrorene Übertrag falsch
    #    stehen blieb (der Genehmigungspfad kennt dafür keine Warnung).
    #  * Ebenso ein Antrag, der einen Eintrag AUS dem Abschlussjahr HERAUS
    #    schiebt (``original_date`` im Jahr, ``proposed_date`` danach) — auch
    #    der bewegt den eingefrorenen Saldo nachträglich.
    # Die Oder-Verknüpfung deckt beide Richtungen ab (hinein UND heraus);
    # ``coalesce`` allein täte das nicht.
    pending_cr_count = db.query(func.count(ChangeRequest.id)).filter(
        ChangeRequest.tenant_id == current_user.tenant_id,
        ChangeRequest.status == ChangeRequestStatus.PENDING,
        or_(
            _in_closing_year(ChangeRequest.proposed_date),
            _in_closing_year(ChangeRequest.original_date),
        ),
    ).scalar() or 0
    if pending_cr_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Jahresabschluss {year} abgelehnt: es gibt noch "
                f"{pending_cr_count} offene Änderungsanträge für dieses Jahr. "
                f"Bitte erst bearbeiten, dann erneut versuchen."
            ),
        )

    # Fix #4: likewise refuse while a PENDING vacation request OVERLAPS the
    # closing year — approving it later would book absences into the year and
    # retroactively move the remaining-vacation balance we are about to freeze.
    from app.models.vacation_request import VacationRequest, VacationRequestStatus
    pending_vr_count = db.query(func.count(VacationRequest.id)).filter(
        VacationRequest.tenant_id == current_user.tenant_id,
        VacationRequest.status == VacationRequestStatus.PENDING.value,
        VacationRequest.date <= end_of_year,
        func.coalesce(VacationRequest.end_date, VacationRequest.date) >= start_of_year,
    ).scalar() or 0
    if pending_vr_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Jahresabschluss {year} abgelehnt: es gibt noch "
                f"{pending_vr_count} offene Urlaubsanträge für dieses Jahr. "
                f"Bitte erst bearbeiten, dann erneut versuchen."
            ),
        )

    # ABV-14: auch MA OHNE Stundenzählung (#191) einbeziehen — sie führen
    # tagebasiert Urlaub (Pro-rata + Vortrag). create_year_closing liefert für sie
    # Überstunden = 0 und den korrekten Resturlaub-Vortrag; ohne sie ginge ihr
    # Resturlaub beim Jahreswechsel verloren.
    users = db.query(User).filter(
        User.is_active == True,
        User.tenant_id == current_user.tenant_id,
    ).all()

    results = calculation_service.create_year_closing(db, year, users)

    return {
        "year": year,
        "next_year": year + 1,
        "employees": results,
    }


@router.delete("/year-closing/{year}")
def delete_year_closing(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Delete year-end closing: removes all carryover records for year+1
    that were created by the year closing.
    """
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail=f"Ungültiges Jahr: {year} (erlaubt 2000–2100)")

    next_year = year + 1
    # Fix #7: remove ONLY the carryovers this year-closing created — manual
    # carryovers (source='manual', entered via upsert_carryover) must survive.
    deleted = db.query(YearCarryover).filter(
        YearCarryover.year == next_year,
        YearCarryover.tenant_id == current_user.tenant_id,
        YearCarryover.source == "year_closing",
    ).delete(synchronize_session=False)

    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Kein Jahresabschluss für {year} gefunden")

    db.commit()

    return {
        "year": year,
        "next_year": next_year,
        "deleted_count": deleted,
    }
