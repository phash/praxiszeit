from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator
from typing import Any, List, Literal, Optional
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from app.schemas.validators import validate_week_blocks
from app.services import work_blocks_service

# Spec 11.4: blocks + weekly_hours/hours_* im selben Body.
BLOCKS_WITH_HOURS_DETAIL = "Tagesstunden werden aus den Arbeitszeit-Blöcken abgeleitet."
_HOURS_INPUT_FIELDS = frozenset({"weekly_hours", *work_blocks_service.HOURS_FIELDS})

# Spec 9.5 / 19.1 Nr. 7: Schlüssel eingefroren; Beschriftungen leben in
# reclamp_audit.REASON_TYPES.
RetroReasonType = Literal["erfassungsfehler", "einvernehmlich", "sonstiges"]

# Plausibilitätsgrenze des Wirkungsdatums (Review Task 10) — dieselben Jahre wie
# ``admin_carryovers`` (2000–2100). Chrome/Edge melden beim Tippen der Jahreszahl
# Zwischenwerte (``0002-…``, ``0020-…``, ``0202-…``) als vollständiges Datum; ohne
# Grenze rechnete der Rechenpfad über Jahrhunderte (73 s je Vorschau, beim Jahr 1
# ``OverflowError`` → 500). Speichern → deutsche 422, Vorschau → wie ein
# fehlendes Datum (``effective_from_plausible`` im Router, vor jeder Rechnung).
EFFECTIVE_FROM_MIN = date(2000, 1, 1)
EFFECTIVE_FROM_MAX = date(2100, 12, 31)
EFFECTIVE_FROM_RANGE_DETAIL = "Das Wirkungsdatum muss zwischen dem 01.01.2000 und dem 31.12.2100 liegen."


def effective_from_plausible(value: date) -> bool:
    """DIE eine Grenze für Anlegen (Validator) und Vorschau (Router)."""
    return EFFECTIVE_FROM_MIN <= value <= EFFECTIVE_FROM_MAX


class TimeBlockIn(BaseModel):
    """Ein Block „von–bis" als ``"HH:MM"`` (Raster und Reihenfolge prüft
    ``validate_week_blocks`` mit deutschem Text). Kein String (z. B. ``8``) →
    Pydantic-Typfehler, den ``_schedule_input_error`` als „Mo, Block 1, Beginn:
    ungültiger Wert." meldet (Spec 3.4)."""
    start: str
    end: str


class DayBlocksIn(BaseModel):
    """Ein Wochentag. Bewusst OHNE ``max_length``/``ge``: „höchstens drei Blöcke"
    und die Pausenregeln meldet ``validate_week_blocks`` mit dem Wortlaut aus 3.4 —
    eine Pydantic-Feldgrenze käme mit englischer Meldung zuerst.

    ``pause_minutes`` ist deshalb auch UNTYPISIERT: als ``int`` wandelte Pydantic
    ``"30"``, ``30.0`` und ``True`` still in eine Zahl um, und die Regel „ganzzahlig —
    kein bool, keine Zeichenkette, keine Kommazahl" (3.4) liefe ins Leere. Der Typ
    wird allein in ``validate_week_blocks`` geprüft (wortgleich mit dem
    Frontend-Zwilling)."""
    blocks: List[TimeBlockIn] = Field(default_factory=list)
    pause_minutes: Optional[Any] = None


class RetroReasonFields(BaseModel):
    """Spec 9.5/11.2: Schutzpaket — Pflicht, sobald die Änderung (bzw. das
    Löschen) nach 9.5 (a)–(c) verkürzt. Gleicher Body für Anlegen und DELETE."""
    retroactive_reason_type: Optional[RetroReasonType] = None
    retroactive_reason_text: Optional[str] = Field(None, min_length=10, max_length=400)  # P15
    wage_risk_confirmed: bool = False
    other_reason_risk_confirmed: bool = False  # P26: Pflicht bei „sonstiges"

    @field_validator('retroactive_reason_text', mode='before')
    @classmethod
    def strip_reason_text(cls, value):
        """P15: die 10–400 Zeichen zählen den Text, nicht umgebende Leerzeichen —
        ``compose_change_note`` speichert die Begründung ohnehin getrimmt."""
        return value.strip() if isinstance(value, str) else value


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


class WorkingHoursChangeCreate(WorkingHoursChangeBase, RetroReasonFields):
    # Spec 11.2: gesetzt → Block-Modus; Soll wird abgeleitet (4.1/4.2).
    blocks: Optional[List[DayBlocksIn]] = None
    remove_legacy_window: bool = False   # P2: Altfenster ausdrücklich entfernen
    reset_of_change_id: Optional[UUID] = None  # P13: „auf vorherigen Stand zurücksetzen"

    def blocks_json(self) -> Optional[list]:
        """Kanonische JSON-Woche (Spec 3.1) oder ``None``."""
        return None if self.blocks is None else [d.model_dump() for d in self.blocks]

    @field_validator('effective_from')
    @classmethod
    def check_effective_from_range(cls, value: date) -> date:
        """Review Task 10: nur am Create-Schema — beim LESEN (``Response``) soll
        eine Bestandszeile nie an einer Eingabegrenze scheitern."""
        if not effective_from_plausible(value):
            raise ValueError(EFFECTIVE_FROM_RANGE_DETAIL)
        return value

    # Reihenfolge zählt: Pydantic führt die ``after``-Validatoren einer Klasse in
    # Definitionsreihenfolge aus — ``derive_from_blocks`` muss das Soll setzen,
    # BEVOR ``check_mode`` den Tagesplan prüft und ``weekly_hours`` summiert.
    @model_validator(mode='after')
    def derive_from_blocks(self):
        """Spec 4.2/11.2: Blöcke streng prüfen und das Soll ABLEITEN. Ein
        mitgeschickter ``weekly_hours``/``hours_*``-Wert neben ``blocks`` ist ein
        Widerspruch → 422 (anders als ``UserCreate``, das überschreibt).
        ``use_daily_schedule``/``work_days_per_week`` aus dem Body werden still
        überschrieben — sie folgen aus den Blöcken."""
        if self.blocks is None:
            return self
        if self.model_fields_set & _HOURS_INPUT_FIELDS:
            raise ValueError(BLOCKS_WITH_HOURS_DETAIL)
        week = validate_week_blocks(self.blocks)
        derived = work_blocks_service.derive_targets(week)
        self.blocks = [DayBlocksIn.model_validate(d) for d in week]
        self.use_daily_schedule = True
        for field in work_blocks_service.HOURS_FIELDS:
            setattr(self, field, float(derived[field]))
        self.weekly_hours = float(derived["weekly_hours"])
        self.work_days_per_week = derived["work_days_per_week"]
        return self

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

    @model_validator(mode='after')
    def check_note_length(self):
        """Spec 9.5: Grund (mit Präfix) + Notiz ≤ 500 Zeichen (``note`` ist
        ``String(500)``) — keine stille Kürzung. Geprüft wird jeder Text, den der
        Schreibpfad über ``compose_change_note`` speichern KANN: ob die Änderung
        verkürzt (und der Grund davorkommt), weiß erst der Router. Verkürzt sie
        nicht, landet die Notiz allein und ungetrimmt in der Spalte — die braucht
        deshalb immer ihre eigene Prüfung, sonst bricht PostgreSQL mit 22001 ab
        (HTTP 500, Review Task 3). Lokaler Import: ``reclamp_audit`` zieht den
        Export-Service."""
        from app.services.reclamp_audit import (
            NOTE_MAX_LENGTH, NOTE_ONLY_TOO_LONG_DETAIL, NOTE_TOO_LONG_DETAIL, compose_change_note,
        )
        if self.retroactive_reason_type and self.retroactive_reason_text:
            composed = compose_change_note(self.note, self.retroactive_reason_type, self.retroactive_reason_text)
            if composed is not None and len(composed) > NOTE_MAX_LENGTH:
                raise ValueError(NOTE_TOO_LONG_DETAIL)
        alone = compose_change_note(self.note, None, None)
        if alone is not None and len(alone) > NOTE_MAX_LENGTH:
            raise ValueError(NOTE_ONLY_TOO_LONG_DETAIL)
        return self


class WorkingHoursChangeDelete(RetroReasonFields):
    """Spec 9.7/P8: optionaler JSON-Body von ``DELETE …/working-hours-changes/{id}``
    — dieselben Schutzpaket-Felder wie beim Anlegen."""


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
    # Spec 11.1: Anzahl neu gekappter bzw. übersprungener Zeiteinträge (Toast).
    # Gleiches Muster wie ``adjusted_absences``: transientes Attribut, sonst 0.
    adjusted_time_entries: int = 0
    skipped_time_entries: int = 0
    # Spec 11.1/11.5: Blöcke der Zeile, LOCKER (kein Validator — Altzeilen aus
    # Migration 073 tragen 07:37/23:59). Bewusst nicht auf WorkingHoursChangeBase:
    # das Create-Schema erbte sonst ein ungeprüftes Eingabefeld (PR3 typisiert es).
    blocks: Optional[Any] = None

    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    model_config = ConfigDict(from_attributes=True)


class TimeEntryMonthOut(BaseModel):
    """Spec 11.3 ``time_entry_months``: Summen der neu gekappten Einträge je Monat."""
    month: str            # "2026-09"
    entries: int
    net_before: float
    net_after: float


class TimeEntryChangeOut(BaseModel):
    """Spec 11.3 ``time_entry_changes``: ein neu gekappter Eintrag vorher/nachher
    (vollständig, ohne Obergrenze — E52). ``not_extendable`` (E50): welche Kante
    der neue Plan nicht mehr verlängern konnte."""
    entry_id: str
    date: date
    old_start: Optional[time] = None
    old_end: Optional[time] = None
    old_uncredited: int = 0
    old_net: float = 0.0
    new_start: Optional[time] = None
    new_end: Optional[time] = None
    new_uncredited: int = 0
    new_net: float = 0.0
    not_extendable: Optional[Literal["start", "end", "both"]] = None


class SkippedEntryOut(BaseModel):
    """Spec 11.3 ``skipped_time_entries`` (E49); ``reason`` = Schlüssel aus
    ``reclamp_audit.SKIP_LABELS``."""
    entry_id: str
    date: date
    reason: str


class AbsenceCreditReductionOut(BaseModel):
    """Spec 9.6/11.3: eine durch F1 STÄRKER als das Tagessoll gesenkte Gutschrift."""
    absence_id: str
    date: date
    old_hours: float
    new_hours: float


class ArbzgFindingsOut(BaseModel):
    """Spec 11.3/P22: geänderte ArbZG-Befunde im Wirkungsbereich."""
    days_over_10_credited_before: int = 0
    days_over_10_credited_after: int = 0
    days_over_10_presence: int = 0
    weeks_over_48_credited_before: int = 0
    weeks_over_48_credited_after: int = 0
    weeks_over_48_presence: int = 0


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
      spätesten gebuchten Abwesenheit bzw. zum spätesten Zeiteintrag (Spec 9.1:
      die Neukappung muss jeden erfassten Eintrag erreichen), mindestens bis
      heute bzw. zum Wirkungsdatum. Früher hart auf „heute" geklemmt — das
      verschwieg genau die künftigen Abwesenheiten, die das Speichern trotzdem
      umschreibt.
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
      Rollback, kein zweiter Rechenpfad.

      Der Dry-Run entfällt (und „nachher" == „vorher", ``affected_absences``
      == 0) in zwei Fällen: bei gesetztem ``blocked_reason`` (es gibt nichts zu
      simulieren) und wenn der eingegebene Snapshot dem aktuell gültigen
      entspricht — dann verschiebt die Änderung im gesamten Wirkungsbereich
      kein Tagessoll, das Ergebnis ist also exakt und nicht genähert. Dieser
      zweite Fall ist der Normalzustand des vorbefüllten Dialogs.
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
    # Spec 11.3 (PR3): Neukappung, Verkürzung/Schutzpaket, ArbZG, Plan-Hinweise.
    # Alle mit Vorgabewert — die Vorschau befüllt sie schrittweise (Task 8–11).
    # ``not_extendable_entries`` trägt zusätzlich Datum und Kante für die Anzeige
    # „14.09., Ende 18:15", die ``not_extendable_count`` allein nicht liefert.
    grace_minutes: int = 0
    blocks_current: Optional[Any] = None
    blocks_new: Optional[Any] = None
    changed_weekdays: List[int] = Field(default_factory=list)
    affected_time_entries: int = 0
    time_entry_months: List[TimeEntryMonthOut] = Field(default_factory=list)
    time_entry_changes: List[TimeEntryChangeOut] = Field(default_factory=list)
    skipped_time_entries: List[SkippedEntryOut] = Field(default_factory=list)
    not_extendable_count: int = 0
    not_extendable_entries: List[TimeEntryChangeOut] = Field(default_factory=list)
    is_shortening: bool = False
    shortening_reasons: List[Literal["entries", "saldo", "absence_credit"]] = Field(default_factory=list)
    shortening_closed_years: List[int] = Field(default_factory=list)
    earliest_lossless_date: Optional[date] = None
    earliest_lossless_note: Optional[str] = None
    lost_credited_hours: float = 0.0
    target_delta_hours: float = 0.0
    credited_delta_hours: float = 0.0
    saldo_delta_hours: float = 0.0
    open_day_saldo_delta_hours: float = 0.0
    absence_f1_adjustments: int = 0
    absence_credit_reductions: List[AbsenceCreditReductionOut] = Field(default_factory=list)
    reset_body: Optional[dict] = None
    stale_entries_closed: int = 0
    arbzg_findings: ArbzgFindingsOut = Field(default_factory=ArbzgFindingsOut)
    milog_warning: List[str] = Field(default_factory=list)
    block_break_notices: List[str] = Field(default_factory=list)
