"""Schemas für verkürzte Tage (Teil B): eigenes Datum mit Höchst-Soll in Stunden."""
from datetime import date as date_type, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services import special_days_service


class ReducedDayCreate(BaseModel):
    date: date_type
    label: str = Field(..., min_length=1, max_length=100)
    max_hours: Decimal

    @field_validator("date")
    @classmethod
    def _plausible_date(cls, v):
        # Tippfehler wie 0202-02-12 → deutsche 422 (gleiche Grenze wie die Listen).
        if not (special_days_service.REDUCED_DAY_YEAR_MIN <= v.year
                <= special_days_service.REDUCED_DAY_YEAR_MAX):
            raise ValueError(special_days_service.REDUCED_DAY_DATE_RANGE_DETAIL)
        return v

    @field_validator("label", mode="before")
    @classmethod
    def _strip_label(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("max_hours", mode="before")
    @classmethod
    def _valid_hours(cls, v):
        # ValueError(MAX_HOURS_ERROR) → 422 mit dem deutschen Wortlaut.
        return special_days_service.parse_max_hours(v)


class ReducedDayUpdate(ReducedDayCreate):
    """Vollersatz: dieselben drei Felder wie beim Anlegen."""


class ReducedDayResponse(BaseModel):
    id: str
    date: date_type
    label: str
    max_hours: float
    created_at: datetime
    warning: Optional[str] = None


class ReducedDayPublic(BaseModel):
    """Lese-Endpoint ``GET /api/reduced-days`` (jede angemeldete Person)."""
    date: str
    label: str
    max_hours: float
