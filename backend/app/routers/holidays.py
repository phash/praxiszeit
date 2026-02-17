from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.reports import PublicHolidayResponse
from app.services import holiday_service

router = APIRouter(prefix="/api/holidays", tags=["holidays"])


@router.get("/", response_model=List[PublicHolidayResponse])
def list_holidays(
    year: int = Query(None, description="Year (default: current year)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List public holidays for a specific year.
    Available to all authenticated users.
    """
    year = year or datetime.now().year

    holidays = holiday_service.get_holidays(db, year)

    return holidays


@router.get("/states")
def list_states(
    current_user: User = Depends(get_current_user)
):
    """List supported German federal states for holiday configuration."""
    from app.config import settings
    return {
        "states": holiday_service.get_supported_states(),
        "current_state": settings.HOLIDAY_STATE,
    }
