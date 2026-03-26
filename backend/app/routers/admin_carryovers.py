"""Admin sub-router: Year Carryovers + Year Closing."""

from fastapi import APIRouter, Depends, HTTPException
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
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    carryovers = db.query(YearCarryover).filter(
        YearCarryover.user_id == user_id
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
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="Ungültiges Jahr")

    carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user_id,
        YearCarryover.year == year,
    ).first()

    if carryover:
        carryover.overtime_hours = data.overtime_hours
        carryover.vacation_days = data.vacation_days
    else:
        carryover = YearCarryover(
            user_id=user_id,
            tenant_id=current_user.tenant_id,
            year=year,
            overtime_hours=data.overtime_hours,
            vacation_days=data.vacation_days,
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
        raise HTTPException(status_code=400, detail="Ungültiges Jahr")

    users = db.query(User).filter(
        User.is_active == True,
        User.track_hours == True,
    ).all()

    results = calculation_service.create_year_closing(db, year, users)

    return {
        "year": year,
        "next_year": year + 1,
        "employees": results,
    }
