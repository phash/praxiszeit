from pydantic import BaseModel, ConfigDict, Field, field_serializer
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


class WorkingHoursChangeBase(BaseModel):
    effective_from: date
    weekly_hours: float = Field(..., ge=0, le=60)
    note: Optional[str] = None


class WorkingHoursChangeCreate(WorkingHoursChangeBase):
    pass


class WorkingHoursChangeResponse(WorkingHoursChangeBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    # Task 3 (#Wochenstunden-Dialog): Rückrechnungs-Summary einer rückwirkenden
    # Änderung. Default 0/None fürs GET-Listing (die ORM-Row hat dort kein
    # solches Attribut -> die Defaults greifen, analog AbsenceResponse.warnings).
    # create_working_hours_change setzt beide als transientes Attribut auf die
    # erzeugte Row, BEVOR sie zurückgegeben wird.
    adjusted_absences: int = 0
    warning: Optional[str] = None

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    model_config = ConfigDict(from_attributes=True)


class WorkingHoursChangePreview(BaseModel):
    """Strikt lesende Vorschau vor dem Speichern einer Wochenstunden-Änderung.

    Zeigt, was eine (ggf. rückwirkende) Änderung anfassen WÜRDE — ohne selbst
    etwas zu schreiben. ``blocked_reason``/``closed_year_warning`` == None
    heißt „kein Problem"; ist ``blocked_reason`` gesetzt, würde der
    schreibende POST-Endpoint mit HTTP 400 ablehnen.

    ``closed_years`` listet ALLE im Zeitraum berührten abgeschlossenen Jahre
    (aufsteigend) gemäß Spec; ``closed_year_warning`` bleibt zusätzlich der
    fertige, auf das früheste Jahr bezogene Anzeigetext — beide Felder nutzen
    dieselbe "abgeschlossen"-Definition (``calculation_service.closed_years_in_range``).

    Feldbedeutungen (Release-Review 1.17.0 präzisiert, unverändert im Typ):

    * ``is_retroactive`` — „das Wirkungsdatum liegt VOR heute". Genau die
      Aussage, die der Admin im Warnhinweis liest. NICHT „es wird etwas
      umgeschrieben": auch ein Datum in der Zukunft kann bereits gebuchte
      Abwesenheiten anfassen (genehmigter Urlaub, Betriebsferien, geplante
      Fortbildung).
    * ``period_start``/``period_end`` — der WIRKUNGSBEREICH der Änderung
      (``calculation_service.retarget_window``): ab dem Wirkungsdatum bis zum
      Tag vor der nächsten Stundenänderung, sonst offen und praktisch bis zur
      spätesten gebuchten Abwesenheit (mindestens bis heute). Früher hart auf
      „heute" geklemmt — das verschwieg genau die künftigen Abwesenheiten, die
      das Speichern trotzdem umschreibt.
    * ``affected_absences`` — Zeilen in diesem Bereich, deren ``hours`` sich
      tatsächlich ändern würden (> 0 ⇒ das Speichern schreibt §16-relevante
      Daten um, egal ob das Datum rückwirkend ist).
    * ``current_daily_target``/``new_daily_target`` — vertragliches Tagessoll
      für einen repräsentativen ARBEITSTAG ab dem Wirkungsdatum (nicht für den
      Stichtag selbst: fällt der auf ein Wochenende, wäre beides hart 0).
    """
    is_retroactive: bool
    period_start: date
    period_end: date
    current_daily_target: float
    new_daily_target: float
    affected_absences: int
    blocked_reason: Optional[str] = None
    closed_years: List[int] = Field(default_factory=list)
    closed_year_warning: Optional[str] = None
