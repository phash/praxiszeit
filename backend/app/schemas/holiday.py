"""Schemas for admin-managed custom holidays (Issue #143).

Custom holidays are admin-created local/regional holidays (Schützenfest,
Karneval, …) stored in the same ``public_holidays`` table as the
workalendar-seeded statutory holidays. They reduce Sollzeit identically and
survive a Bundesland resync.
"""
from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HolidayCreate(BaseModel):
    """Payload to create a custom holiday."""
    name: str = Field(..., min_length=1, max_length=255)
    date: date_type

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name darf nicht leer sein")
        return v


class HolidayUpdate(BaseModel):
    """Payload to edit a custom holiday. All fields optional."""
    name: str | None = Field(None, min_length=1, max_length=255)
    date: date_type | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Name darf nicht leer sein")
        return v


class HolidayResponse(BaseModel):
    """Holiday returned to clients (standard + custom)."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: date_type
    name: str
    year: int
    is_custom: bool

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v):
        return str(v)
