from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer
from typing import Optional, List
# #225: alias `date` so the field literally named `date` does not shadow the type.
# With `from datetime import date`, a field `date: Optional[date] = None` makes
# Pydantic 2.13 resolve the annotation in a namespace where `date` is bound to the
# default `None` → `Optional[None]` == NoneType → every edit rejected with
# "Input should be None". holiday.py/vacation_request.py already use this alias.
from datetime import date as date_type, time, datetime
from app.services.timezone_service import today_local
from decimal import Decimal
from uuid import UUID


def _normalize_sunday_reason(v: Optional[str]) -> Optional[str]:
    """#485: §10-Ausnahmegrund einheitlich fuer alle Schreibwege — getrimmt,
    leer bzw. nur Leerzeichen wird NULL (statt eines leeren Strings, der im
    Export als Grund erscheinen wuerde)."""
    if v is None:
        return None
    return v.strip() or None


class TimeEntryBase(BaseModel):
    date: date_type
    start_time: time
    end_time: time
    break_minutes: int = Field(default=0, ge=0)
    note: Optional[str] = None
    sunday_exception_reason: Optional[str] = Field(None, max_length=2000)  # §10 ArbZG (#485: begrenzt)
    # #144 §4 ArbZG: justification when a mandatory break was not possible.
    # Submitted by the client to waive the break-validation block for
    # non-exempt users. Backend enforces non-empty when actually used.
    # SEC-D: cap length to prevent storage DoS via unbounded free text.
    break_waiver_reason: Optional[str] = Field(None, max_length=2000)

    @field_validator('end_time')
    @classmethod
    def validate_end_after_start(cls, v, info):
        if 'start_time' in info.data and v <= info.data['start_time']:
            raise ValueError('Endzeit muss nach Startzeit liegen')
        return v

    @field_validator('date')
    @classmethod
    def validate_not_future(cls, v):
        if v > today_local():
            raise ValueError('Datum darf nicht in der Zukunft liegen')
        return v

    @field_validator('sunday_exception_reason')
    @classmethod
    def _sunday_reason(cls, v):
        return _normalize_sunday_reason(v)


class TimeEntryCreate(TimeEntryBase):
    pass


class TimeEntryUpdate(BaseModel):
    date: Optional[date_type] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = Field(None, ge=0)
    note: Optional[str] = None
    sunday_exception_reason: Optional[str] = Field(None, max_length=2000)  # §10 ArbZG (#485: begrenzt)
    break_waiver_reason: Optional[str] = Field(None, max_length=2000)  # #144 §4 ArbZG (SEC-D: bounded)

    @field_validator('end_time')
    @classmethod
    def validate_end_after_start(cls, v, info):
        if v is not None and 'start_time' in info.data and info.data['start_time'] is not None:
            if v <= info.data['start_time']:
                raise ValueError('Endzeit muss nach Startzeit liegen')
        return v


    @field_validator('sunday_exception_reason')
    @classmethod
    def _sunday_reason(cls, v):
        return _normalize_sunday_reason(v)


class TimeEntryResponse(BaseModel):
    id: UUID
    user_id: UUID
    date: date_type
    start_time: time
    end_time: Optional[time] = None
    break_minutes: int = Field(default=0, ge=0)
    note: Optional[str] = None
    net_hours: float
    is_editable: bool = True
    warnings: List[str] = []
    is_sunday_or_holiday: bool = False
    is_night_work: bool = False
    sunday_exception_reason: Optional[str] = None  # §10 ArbZG
    break_waiver_reason: Optional[str] = None  # #144 §4 ArbZG
    raw_start_time: Optional[time] = None  # #201: unklammerter Stempelzeitpunkt
    raw_end_time: Optional[time] = None    # #201: unklammerter Stempelzeitpunkt
    created_at: datetime

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    model_config = ConfigDict(from_attributes=True)


# --- Clock-in/out schemas ---

class ClockInRequest(BaseModel):
    note: Optional[str] = None


class ClockOutRequest(BaseModel):
    break_minutes: int = Field(default=0, ge=0)
    note: Optional[str] = None
    # M-ARB1: document a §4 break deviation captured during clock-out, mirroring
    # the create/CR paths (#144). #499: ohne ausreichende Pause UND ohne
    # (zulässige) Begründung lehnt der Server das Ausstempeln mit 400 ab — der
    # Eintrag bleibt offen, bis Pause oder Begründung mitkommt.
    break_waiver_reason: Optional[str] = Field(None, max_length=2000)


class ClockStatusResponse(BaseModel):
    is_clocked_in: bool
    current_entry: Optional[TimeEntryResponse] = None
    # Laufzeit (brutto) NUR des offenen Eintrags — Timer der Stempeluhr.
    elapsed_minutes: Optional[int] = None
    # #494: Tages-Ist von heute = Σ net_hours der heute abgeschlossenen Einträge
    # + laufende Netto-Minuten des offenen Eintrags. Ohne den abgeschlossenen
    # Vormittag zeigte die mobile Karte bei geteilten Diensten nur den
    # Nachmittagsblock (bzw. 0:00 nach dem Ausstempeln).
    today_net_minutes: int = 0
    # #494/#431: Tagessoll von heute aus dem datumsaufgelösten Vertrags-Snapshot
    # (nicht aus den Live-Feldern der User-Zeile). Wochenende/track_hours=False → 0.
    today_target_hours: float = 0.0
