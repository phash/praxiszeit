from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, field_serializer
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

from app.schemas.validators import MinuteTime


def _normalize_sunday_reason(v: Optional[str]) -> Optional[str]:
    """#485: §10-Ausnahmegrund einheitlich fuer alle Schreibwege — getrimmt,
    leer bzw. nur Leerzeichen wird NULL (statt eines leeren Strings, der im
    Export als Grund erscheinen wuerde)."""
    if v is None:
        return None
    return v.strip() or None


class TimeEntryBase(BaseModel):
    date: date_type
    # Gesamtreview 1.20 (B1): Sekunden fallen beim Eingang weg (``MinuteTime``).
    start_time: MinuteTime
    end_time: MinuteTime
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
    start_time: Optional[MinuteTime] = None
    end_time: Optional[MinuteTime] = None
    break_minutes: Optional[int] = Field(None, ge=0)
    note: Optional[str] = None
    sunday_exception_reason: Optional[str] = Field(None, max_length=2000)  # §10 ArbZG (#485: begrenzt)
    break_waiver_reason: Optional[str] = Field(None, max_length=2000)  # #144 §4 ArbZG (SEC-D: bounded)

    # Gesamtreview 1.20 (B1): ``Optional`` heißt hier „darf fehlen", nicht „darf
    # null sein". Die MA-Route übernahm ein mitgeschicktes ``null`` per
    # ``setattr`` (500 in Kappung bzw. §3/§4, für Mitarbeitende ein irreführender
    # 403 „vergangene Tage"), die Admin-Route deutete es still als „unverändert".
    # Jetzt 422 für beide; ein weggelassenes Feld bleibt unverändert. Der
    # Validator läuft nur für mitgeschickte Felder.
    # ``end_time`` (Nachzug zu B1): die Spalte ist nullable (offener Eintrag),
    # ein Ende lässt sich aber nicht wieder entfernen — ``{"end_time": null}``
    # öffnete über die MA-Route einen geschlossenen Eintrag wieder (§16-Ende
    # weg, §3/§4 übersprungen, Auto-Close später um 23:59). Ein offener Eintrag
    # bleibt offen, solange ``end_time`` fehlt (so schickt es die Zeiterfassung).
    @field_validator('date', 'start_time', 'end_time', 'break_minutes')
    @classmethod
    def reject_explicit_null(cls, v, info):
        if v is None:
            raise ValueError(
                f"{info.field_name} darf nicht leer sein – zum Beibehalten weglassen"
            )
        return v

    # #502: dieselbe Grenze wie beim Anlegen (``TimeEntryBase.validate_not_future``)
    # — seit Ultrareview 1.20 (Fund 2) aber NICHT mehr hier im Schema, sondern in
    # beiden Bearbeiten-Routen (``time_entries.update_time_entry``,
    # ``admin_time_entries.admin_update_time_entry``) über
    # ``assert_date_change_not_future``: das Schema sieht das gespeicherte Datum
    # nicht und lehnte auch das unverändert mitgeschickte ab (die Formulare
    # schicken es immer mit) — ein künftig datierter Eintrag war dann nicht mehr
    # korrigierbar.

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


FUTURE_DATE_DETAIL = 'Datum darf nicht in der Zukunft liegen'


def assert_date_change_not_future(entry_data: "TimeEntryUpdate", stored_date) -> None:
    """#502 / Ultrareview 1.20 (Fund 2): ein Datums**wechsel** in die Zukunft
    → 422 (für §16 eine erfundene Zeit). Das unverändert mitgeschickte Datum
    eines bereits künftig datierten Eintrags (z. B. aus einem Import vor dieser
    Prüfung) bleibt bearbeitbar."""
    from fastapi import HTTPException

    if ("date" in entry_data.model_fields_set
            and entry_data.date is not None
            and entry_data.date != stored_date
            and entry_data.date > today_local()):
        raise HTTPException(status_code=422, detail=FUTURE_DATE_DETAIL)


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
    # Spec 2026-10-08 (7.1, E79, P18): nur lesend — kein Eingabeschema kennt
    # diese Felder (E11), der Server leitet sie ab.
    uncredited_minutes: int = 0
    credit_override: bool = False
    auto_closed: bool = False
    clamp_grace_minutes: Optional[int] = None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def not_credited_minutes(self) -> int:
        """P19: Lücke + von der Hülle gekappte Anwesenheit — DIE eine Quelle
        ``work_window_service.not_credited_minutes`` (lokal importiert: ein
        Schema zieht beim Modulimport keine Services)."""
        from app.services.work_window_service import not_credited_minutes
        return not_credited_minutes(self)

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


class ClockBlock(BaseModel):
    """Spec 2026-10-08, 8.4/14: ein Arbeitszeit-Block eines Tages (``/clock-status``:
    heute; ``/day-blocks``: das angefragte Datum)."""
    start: str  # "HH:MM"
    end: str    # "HH:MM"


class DayBlocksResponse(BaseModel):
    """Gesamtreview 1.20 B6 (PR2 Task 17): Blöcke und Puffer eines beliebigen
    Tages der eigenen Person — für die §4-Vorprüfung und die Pausen-Automatik der
    Zeiterfassung an Tagen ≠ heute (dort fehlten sie, das Formular rechnete ohne
    Blöcke). ``grace_minutes`` = aktueller Mandanten-Puffer, mit dem eine
    Neuanlage kappt (ein gespeicherter Eintrag bringt seinen eigenen mit, E80)."""
    date: date_type
    blocks: List[ClockBlock] = []
    grace_minutes: int = 15


class ClockStatusResponse(BaseModel):
    is_clocked_in: bool
    current_entry: Optional[TimeEntryResponse] = None
    # Laufzeit (brutto) NUR des offenen Eintrags — Timer der Stempeluhr.
    elapsed_minutes: Optional[int] = None
    # #494: Tages-Ist von heute = Σ net_hours der heute abgeschlossenen Einträge
    # + laufende Netto-Minuten des offenen Eintrags. Ohne den abgeschlossenen
    # Vormittag zeigte die mobile Karte bei geteilten Diensten nur den
    # laufenden Nachmittagseintrag (bzw. 0:00 nach dem Ausstempeln).
    today_net_minutes: int = 0
    # #494 F1: heute zu stempelnde Stunden aus
    # ``calculation_service.get_day_presence_target`` — 0 am Wochenende, an
    # Feiertagen, bei ganztägiger Abwesenheit jeden Typs, außerhalb des
    # Beschäftigungsfensters und ohne Stundenzählung; Halbtag und Sondertag
    # anteilig (Basis: der Vertrags-Snapshot #431). Kein Vertrags-Tagessoll,
    # nie für Saldo, Exporte oder Journal.
    today_target_hours: float = 0.0
    # Spec 2026-10-08 (8.4, 11.1, 14): die Blöcke von heute — für die §4-Vorprüfung
    # im StampWidget und den Dashboard-Status in der Lücke (E69) — und der
    # Puffer, mit dem das Ausstempeln kappen wird (E80). In JEDEM Zweig.
    blocks_today: List[ClockBlock] = []
    grace_minutes: int = 15
    # Gesamtreview 1.20 (Fund 24): der AKTUELLE Mandanten-Puffer, mit dem eine
    # Neuanlage kappt (E80) — für die §4-Vorprüfung und die Pausen-Automatik der
    # Zeiterfassung. Eingestempelt weicht ``grace_minutes`` (Puffer des offenen
    # Eintrags) davon ab, sobald die Verwaltung den Puffer nach dem Einstempeln
    # ändert; nicht eingestempelt sind beide gleich.
    tenant_grace_minutes: int = 15
