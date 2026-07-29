from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


class WorkingHoursChangeBase(BaseModel):
    """#431: die Zeile ist ein vollstaendiger Vertrags-Snapshot ab
    ``effective_from`` — Modus, Tageswerte, Arbeitstage und Wochenstunden.

    ``weekly_hours`` ist deshalb Optional: im Tagesplan-Modus schickt der Client
    keinen eigenen Wert, der Server setzt ihn als Summe der Tageswerte (siehe
    ``WorkingHoursChangeCreate.check_mode``). Persistiert ist er immer.
    """
    effective_from: date
    weekly_hours: Optional[float] = Field(None, ge=0, le=60)
    use_daily_schedule: bool = False
    hours_monday: Optional[float] = Field(None, ge=0, le=24)
    hours_tuesday: Optional[float] = Field(None, ge=0, le=24)
    hours_wednesday: Optional[float] = Field(None, ge=0, le=24)
    hours_thursday: Optional[float] = Field(None, ge=0, le=24)
    hours_friday: Optional[float] = Field(None, ge=0, le=24)
    work_days_per_week: Optional[int] = Field(None, ge=1, le=7)
    note: Optional[str] = None


class WorkingHoursChangeCreate(WorkingHoursChangeBase):
    @model_validator(mode='after')
    def check_mode(self):
        """Die beiden Modi schliessen einander aus — und der jeweils andere
        Satz Felder waere inert.

        Bewusst NUR am Create-Schema, nicht an ``WorkingHoursChangeBase``: ein
        ``mode='after'``-Validator wuerde sonst auch beim LESEN
        (``from_attributes``) laufen und dort (a) eine Bestandszeile mit
        inerten Werten in einen HTTP 500 verwandeln und (b) ``weekly_hours``
        aus den Tageswerten neu berechnen — also einen anderen Wert anzeigen,
        als in der §16-relevanten Zeile steht.
        """
        days = [self.hours_monday, self.hours_tuesday, self.hours_wednesday,
                self.hours_thursday, self.hours_friday]
        if self.use_daily_schedule:
            if not any(d for d in days if d):
                raise ValueError("Im Tagesplan-Modus muss mindestens ein Wochentag Stunden haben.")
            total = sum(d or 0 for d in days)
            if total > 60:
                raise ValueError("Die Summe der Tagesstunden darf 60 nicht überschreiten.")
            self.weekly_hours = round(total, 2)
        else:
            if self.weekly_hours is None:
                raise ValueError("Wochenstunden sind im gleichmäßigen Modus Pflicht.")
            for d in days:
                if d is not None:
                    raise ValueError("Tagesstunden gehören zum Tagesplan-Modus.")
        return self


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
    * ``day_targets_current``/``day_targets_new`` (#431) — das Tagessoll je
      Wochentag, Montag bis Freitag, vor und nach der Änderung. EIN Skalar
      bildet einen individuellen Tagesplan nicht ab: „Tagessoll 5,67 h → 4,33 h"
      sagt über eine Änderung von Mo 8/Di 5/Mi 4 auf Mo 4/Di 5/Mi 4 nichts
      Brauchbares aus. Nicht geplante Tage stehen als ``0.0`` drin (die Liste
      ist immer fünf Einträge lang, Index 0 = Montag).
    * ``current_daily_target``/``new_daily_target`` — Teil der bestehenden API
      und deshalb erhalten: das MITTEL der Tage mit Soll > 0 (``0.0``, wenn
      keiner). Bewusst nicht der Mittelwert über alle fünf Wochentage — ein
      freier Donnerstag/Freitag zöge den Wert sonst künstlich nach unten. Für
      Mitarbeitende ohne Tagesplan ist das unverändert das gleichmäßige
      Tagessoll. Früher war es das Soll eines „repräsentativen Arbeitstags"
      (nicht des Stichtags — der kann auf ein Wochenende fallen); die
      Wochenend-Falle bleibt durch die Wochentags-Betrachtung ausgeschlossen.
    * ``overtime_before``/``overtime_after`` und
      ``vacation_days_before``/``vacation_days_after`` (#431) — Überstundensaldo
      (Stichtag #313) und verbrauchte Urlaubstage des Jahres von
      ``period_start``, jeweils im Ist-Zustand und im simulierten Zustand NACH
      dem Speichern. Beide „nachher"-Werte stammen aus DEMSELBEN, wieder
      zurückgerollten Dry-Run wie ``affected_absences`` — ein Flush, ein
      Rollback, kein zweiter Rechenpfad. Bei gesetztem ``blocked_reason`` sind
      sie identisch mit den „vorher"-Werten (es gibt nichts zu simulieren).
    """
    is_retroactive: bool
    period_start: date
    period_end: date
    current_daily_target: float
    new_daily_target: float
    day_targets_current: List[float]
    day_targets_new: List[float]
    overtime_before: float
    overtime_after: float
    vacation_days_before: float
    vacation_days_after: float
    affected_absences: int
    blocked_reason: Optional[str] = None
    closed_years: List[int] = Field(default_factory=list)
    closed_year_warning: Optional[str] = None
