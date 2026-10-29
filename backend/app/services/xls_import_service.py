"""
Service für den Import historischer Zeiterfassungsdaten aus TimeRec-XLS-Dateien.
Dateiformat: Sheet "Zeiterfassung", Spalten: Datum, Tag, Total, Ein, Aus, Tagesnotiz
"""
import uuid
import xlrd
from bisect import bisect_left
from datetime import datetime, timedelta, date, time
from types import SimpleNamespace
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from pydantic import BaseModel, computed_field

from app.models import TimeEntry, TimeEntryAuditLog, User
from app.schemas.validators import MinuteTime
from app.services.arbzg_utils import is_night_work
from app.services import presence_service, work_window_service
from app.services.timezone_service import today_local
from app.services.break_validation_service import (
    BreakBlock, break_block_for_entry, break_block_for_new, daily_break_figures,
)

EXCEL_EPOCH = datetime(1899, 12, 30)
MAX_DAILY_NET_HOURS = 10.0   # §3 ArbZG
MIN_REST_HOURS = 11.0        # §5 ArbZG
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# Spec 2026-10-08 P3: Hinweis in der Vorschau, wenn die Zeile einen anerkannten
# Eintrag überschreibt — die neuen Zeiten werden dann ungekappt angerechnet.
CREDIT_OVERRIDE_IMPORT_NOTE = (
    "Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet."
)


def employment_window_skip_reason(user, d: date) -> Optional[str]:
    """Grund, warum eine Zeile mit Datum ``d`` außerhalb des Beschäftigungsfensters
    der Zielperson liegt — sonst None (Gesamtreview 1.20, Parallelpfad zu #502).

    Einstempeln, beide Anlege-/Bearbeiten-Routen und die Antragsgenehmigung
    lehnen ein solches Datum mit 400 ab (``time_entries._assert_within_employment_window``,
    gleicher Wortlaut, hier mit Datum wie bei den Abwesenheiten). Der Import
    speicherte die Zeile bis dahin still, und sie fiel danach aus dem
    gefensterten Ist (#195) heraus. Jetzt überspringt er sie sichtbar — wie
    Zeilen mit Ende ≤ Beginn."""
    first = getattr(user, "first_work_day", None)
    last = getattr(user, "last_work_day", None)
    if first and d < first:
        return f"Datum liegt vor dem ersten Arbeitstag ({first.strftime('%d.%m.%Y')})"
    if last and d > last:
        return f"Datum liegt nach dem letzten Arbeitstag ({last.strftime('%d.%m.%Y')})"
    return None


def import_skip_reason(user, d: date) -> Optional[str]:
    """Grund, warum der Import eine Zeile mit Datum ``d`` überspringt — sonst None.

    Ultrareview 1.20 (Fund 2): ein Datum nach heute lehnen alle anderen
    Schreibwege ab (``TimeEntryBase.validate_not_future``, Datumswechsel beim
    Bearbeiten); ``/confirm`` legte solche Zeilen still an. Danach das
    Beschäftigungsfenster (``employment_window_skip_reason``). Dieselbe
    Behandlung: sichtbar überspringen, vor der Eintragssuche (ersetzt keinen
    Bestand), zählt für keinen Tag."""
    if d > today_local():
        return "Datum liegt in der Zukunft"
    if user is None:
        return None
    return employment_window_skip_reason(user, d)


class ImportedEntryIn(BaseModel):
    """Eine Importzeile, wie ``/confirm`` sie annimmt (Eingabe).

    Spec 2026-10-08 E11 / 7.1 („``ImportedEntry``-Eingabe"): Felder, die der
    Server selbst ableitet (``uncredited_minutes`` usw.), gibt es hier nicht —
    ein mitgeschickter Wert fällt beim Einlesen weg (Pydantic ``extra=ignore``)."""
    date: date
    # Gesamtreview 1.20 (B1): ``/confirm`` nimmt die Zeilen vom Client — wie die
    # Datei (``parse_xls`` schneidet Sekunden ab) minutengenau (``MinuteTime``).
    start_time: MinuteTime
    end_time: MinuteTime
    break_minutes: int
    note: Optional[str]
    has_conflict: bool
    arbzg_warnings: list[str]
    raw_start_time: Optional[MinuteTime] = None
    raw_end_time: Optional[MinuteTime] = None


class ImportedEntry(ImportedEntryIn):
    """Eine Zeile der Vorschau (Ausgabe von ``parse_xls``)."""
    # Spec 2026-10-08 (7.1 Nr. 11): nur ANZEIGE der Vorschau. ``/confirm``
    # nimmt den Wert nicht an (E11) — ``_execute_import_inner`` rechnet neu.
    uncredited_minutes: int = 0
    # Spec 7.4 (PR2): Netto der Vorschau vom Server — ImportXls.tsx rechnet nicht
    # mehr selbst. Nur Anzeige; /confirm rechnet neu (wie ``uncredited_minutes``).
    net_hours: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def not_credited_minutes(self) -> int:
        """P19: „nicht angerechnet" der Vorschauzeile = Lücke + von der Hülle
        gekappte Anwesenheit — DIE eine Quelle wie ``TimeEntryResponse``, damit
        ImportXls.tsx nie ``uncredited_minutes`` allein als „nicht angerechnet"
        ausweist. Nur Anzeige (E11)."""
        return work_window_service.not_credited_minutes(self)


class ImportResult(BaseModel):
    imported: int
    skipped: int
    overwritten: int
    warnings: list[str]


def _excel_serial_to_datetime(serial: float) -> datetime:
    """Konvertiert Excel-Serial-Datetime zu Python-datetime. Basis: 1899-12-30."""
    return EXCEL_EPOCH + timedelta(days=serial)


def _day_break_minutes(
    rows: Sequence[tuple[time, time, Sequence[int]]],
    kept: Sequence[BreakBlock] = (),
) -> list[int]:
    """ArbZG §4: Auto-Pause je TAG aus der ANGERECHNETEN Zeit (Spec 7.4, #499).

    ``rows`` = die Importzeilen eines Tages als ``(eff_start, eff_end, segments)``
    (``segments`` = ``work_window_service.gap_segments`` der Zeile), ``kept`` =
    ``BreakBlock`` der Einträge desselben Tages, die stehen bleiben. Bedarf und
    Deckung nach DERSELBEN Regel wie ``validate_daily_break``
    (``daily_break_figures``): Bedarf aus der angerechneten Zeit des Tages,
    gedeckt durch erfasste Pausen, Abstände zwischen Einträgen und
    Lückensegmente von je mindestens 15 Min. Nachgetragen wird nur, was fehlt —
    sonst zöge der Import eine Pause in der Lücke ein zweites Mal ab
    (Doppelabzug, E45).

    Der Rest steht an der längsten Zeile (bei Gleichstand an der ersten): dort
    liegt die Pause am ehesten, und eine kurze Zeile verlöre sonst den größten
    Teil ihrer Zeit. Eine Zeile trägt höchstens ihre angerechneten Minuten
    (``end − start − deduct_minutes``) — sonst stünde im §16-Beleg eine Pause,
    die nicht in den Eintrag passt. Reicht die längste nicht, kommen die
    nächstlängeren dazu, so wenige wie möglich; jedes Stück ist mindestens
    15 Min lang (§4 Satz 2 — ein Rest unter 15 wird so auf 15 aufgerundet), eine
    Zeile unter 15 Min trägt keins. Was die Zeilen der Datei nicht tragen
    können (kurze Zeile neben langem Bestand), bucht der Import nicht — bleibt
    so ein Fehlbetrag (``_day_break_shortfall``), übernimmt der Import den
    ganzen Tag nicht (Gesamtreview 1.20 B11).

    Gesamtreview 1.20 (B4): bis hierher je ZEILE gerechnet — ein geteilter
    Dienst aus zwei Zeilen unter 6 h bekam gar keine Pause, zwei Zeilen über 6 h
    bekamen je eine (der Abstand dazwischen zählte nicht). Review-Nachzug: der
    ganze Rest stand an der längsten Zeile, auch wenn sie kürzer war (Bestand
    08:00–17:00 + Zeile 17:00–17:20 → „Pause 45 Min" am 20-Minuten-Eintrag).
    Note: assumes end > start (no overnight shifts) — TimeRec liefert keine."""
    if not rows:
        return []
    own = [break_block_for_new(s, e, 0, segs) for s, e, segs in rows]
    credited, covered = daily_break_figures(list(kept) + own)
    required = 45 if credited > 9 * 60 else 30 if credited > 6 * 60 else 0
    rest = max(0, required - covered)
    breaks = [0] * len(rows)
    if not rest:
        return breaks
    caps = [b.end - b.start - b.deduct_minutes for b in own]
    order = [i for i in sorted(range(len(own)), key=lambda i: (-caps[i], i)) if caps[i] >= 15]
    used, carry = [], 0
    for i in order:
        if carry >= rest:
            break
        used.append(i)
        carry += caps[i]
    # Je Zeile 15 Min, der Rest bis zum Bedarf (höchstens, was die Zeilen tragen)
    # längste zuerst obendrauf.
    extra = min(rest, carry) - 15 * len(used)
    for i in used:
        add = max(0, min(extra, caps[i] - 15))
        breaks[i] = 15 + add
        extra -= add
    return breaks


def _calc_break_minutes(eff_start: time, eff_end: time, segments: Sequence[int]) -> int:
    """Auto-Pause einer einzelnen Zeile ohne weitere Einträge am Tag — der
    Sonderfall von ``_day_break_minutes`` (eine Regel, kein Nachbau)."""
    return _day_break_minutes([(eff_start, eff_end, segments)])[0]


def _day_break_shortfall(
    rows: Sequence[tuple[time, time, Sequence[int], int]],
    kept: Sequence[BreakBlock] = (),
) -> int:
    """§4-Fehlbetrag des Tages in Minuten NACH der Automatik-Pause — 0, wenn die
    Pausenpflicht gedeckt ist.

    ``rows`` = ``(eff_start, eff_end, segments, break_minutes)`` je Importzeile
    mit der Pause aus ``_day_break_minutes``, ``kept`` wie dort. Dieselbe Regel
    wie die §4-Tagesprüfung der Vorschau (``_check_arbzg``) und
    ``validate_daily_break`` (``daily_break_figures``): die eingetragene Pause
    senkt die angerechnete Zeit und damit ggf. den Bedarf."""
    blocks = list(kept) + [break_block_for_new(s, e, b, segs) for s, e, segs, b in rows]
    credited, covered = daily_break_figures(blocks)
    required = 45 if credited > 9 * 60 else 30 if credited > 6 * 60 else 0
    return max(0, required - covered)


def break_shortfall_skip_reason(missing_minutes: int) -> str:
    """Grund, warum der Import einen Tag nicht übernimmt (Gesamtreview 1.20 B11,
    Produktentscheidung 2026-10-17): nach der Automatik-Pause fehlt noch Pause
    nach §4 ArbZG — die Zeilen der Datei können sie nicht tragen (z. B. eine
    kurze Zeile neben einem langen vorhandenen Eintrag). Der Import kennt keine
    Begründung, kann also keine §4-Ausnahme belegen — unabhängig vom Schalter
    ``break_exception_allowed``. Ohne Schlusspunkt, wie
    ``employment_window_skip_reason``."""
    return (
        f"die Pause nach § 4 ArbZG lässt sich mit den Zeilen dieses Tages nicht "
        f"abziehen (es fehlen {missing_minutes} Min). Bitte den Tag von Hand erfassen"
    )


NIGHT_WORKER_MAX_NET_HOURS = 8.0  # §6 Abs. 2 ArbZG: Nachtarbeitnehmer


def _check_arbzg(
    entry_date: date,
    start: time,
    end: time,
    break_min: int,
    prev_end_dt: Optional[datetime],
    exempt: bool = False,
    is_night_worker: bool = False,
    same_day_blocks: Optional[list[BreakBlock]] = None,
    *,
    uncredited_segments: Sequence[int],
    rest_start: Optional[time] = None,
    check_day: bool = True,
    next_rest: Optional[tuple[datetime, datetime]] = None,
) -> list[str]:
    """ArbZG-Warnungen ermitteln (§3 Tageslimit, §4 Pause, §5 Ruhezeit, §6 Nachtarbeit).

    exempt=True (§18 ArbZG): alle Prüfungen werden übersprungen.
    is_night_worker=True (§6 Abs. 2 ArbZG): 8h-Limit statt 10h.
    same_day_blocks: ``BreakBlock`` der anderen Einträge desselben Tages (Import-
        Batch + vorhandene DB). Wenn übergeben, werden §3 und §4 auf Basis der
        Tages-Aggregation bewertet — mit derselben Regel wie
        ``validate_daily_break`` (``daily_break_figures``), kein vierter Nachbau.
    uncredited_segments: Lückensegmente dieses Eintrags (Spec 8.2) — nicht
        angerechnete Zeit ist keine Arbeitszeit, Segmente >= 15 Min zählen als Pause.
    rest_start: Beginn für §5, der ROHSTEMPEL (``raw_start or start``) wie in
        ``rest_time_service`` (Spec 7.3); ohne Angabe ``start``.
    check_day: False → keine §3/§4-Prüfung an dieser Zeile (die Vorschau prüft
        den Tag einmal, an seiner letzten Zeile — Gesamtreview 1.20 B4).
    next_rest: (Arbeitsende dieses Tages, erster Beginn des nächsten Arbeitstags)
        — §5 bis zu einem Tag, den nur der Bestand trägt (``_rest_reference``).
    """
    if exempt:
        return []

    warnings = []
    own = break_block_for_new(start, end, break_min, uncredited_segments)
    net_hours = (own.end - own.start - own.deduct_minutes) / 60.0 - break_min / 60.0

    if not check_day:
        pass
    elif same_day_blocks:
        # §3 / §4 Aggregation: alle Blöcke des Tages zusammenfassen (inkl. diesem Eintrag)
        total_net_min, total_effective_break = daily_break_figures(list(same_day_blocks) + [own])
        total_net_hours = total_net_min / 60.0

        # §3 / §6 Abs. 2 auf Tagesbasis
        if is_night_worker and total_net_hours > NIGHT_WORKER_MAX_NET_HOURS:
            warnings.append(
                f"§6 Abs. 2 ArbZG: Nachtarbeitnehmer — Tages-Netto-Arbeitszeit {total_net_hours:.1f}h überschreitet 8h-Limit"
            )
        elif total_net_hours > MAX_DAILY_NET_HOURS:
            warnings.append(
                f"§3 ArbZG: Tages-Netto-Arbeitszeit {total_net_hours:.1f}h überschreitet das 10h-Tageslimit"
            )

        # §4 Pausenpflicht auf Tagesbasis
        if total_net_min > 540 and total_effective_break < 45:
            warnings.append(
                f"§4 ArbZG: Tages-Netto-Arbeitszeit {total_net_hours:.1f}h erfordert mindestens 45 Minuten Pause "
                f"(Gesamtpause: {total_effective_break} Minuten)"
            )
        elif total_net_min > 360 and total_effective_break < 30:
            warnings.append(
                f"§4 ArbZG: Tages-Netto-Arbeitszeit {total_net_hours:.1f}h erfordert mindestens 30 Minuten Pause "
                f"(Gesamtpause: {total_effective_break} Minuten)"
            )
    else:
        # Einzeleintrag: §3 / §6 Abs. 2 nur anhand dieses Eintrags
        if is_night_worker and net_hours > NIGHT_WORKER_MAX_NET_HOURS:
            warnings.append(
                f"§6 Abs. 2 ArbZG: Nachtarbeitnehmer — Netto-Arbeitszeit {net_hours:.1f}h überschreitet 8h-Limit"
            )
        elif net_hours > MAX_DAILY_NET_HOURS:
            # §3: allgemeines 10h-Tageslimit
            warnings.append(
                f"§3 ArbZG: Netto-Arbeitszeit {net_hours:.1f}h überschreitet das 10h-Tageslimit"
            )

    if is_night_work(start, end):
        # §6 Abs. 1: Nachtarbeit-Erkennung (>2h zwischen 23:00–06:00)
        warnings.append("§6 ArbZG: Nachtarbeit (>2h in der Nachtzeit 23:00–06:00)")

    if prev_end_dt is not None:
        curr_start_dt = datetime.combine(entry_date, rest_start or start)
        rest_hours = (curr_start_dt - prev_end_dt).total_seconds() / 3600.0
        if rest_hours < MIN_REST_HOURS:
            warnings.append(
                f"§5 ArbZG: Ruhezeit {rest_hours:.1f}h unterschreitet das 11h-Minimum "
                f"(vorheriger Eintrag endete {prev_end_dt.strftime('%d.%m.%Y %H:%M')})"
            )

    if next_rest is not None:
        day_end_dt, next_start_dt = next_rest
        rest_hours = (next_start_dt - day_end_dt).total_seconds() / 3600.0
        if rest_hours < MIN_REST_HOURS:
            warnings.append(
                f"§5 ArbZG: Ruhezeit {rest_hours:.1f}h unterschreitet das 11h-Minimum "
                f"(nächster vorhandener Eintrag beginnt {next_start_dt.strftime('%d.%m.%Y %H:%M')})"
            )

    return warnings


def _find_existing_entry(
    db: Session,
    user_id: uuid.UUID,
    tenant_id,
    d: date,
    *,
    starts: Sequence[time],
    raw_start: time,
) -> Optional[TimeEntry]:
    """Der Eintrag, den eine Importzeile überschreiben würde.

    Reihenfolge:
    1. ``start_time`` == einer der ``starts`` (angerechneter Beginn der Zeile,
       bei ``/confirm`` zusätzlich der vom Client gelieferte) — Verhalten bis 1.19.3;
    2. ``raw_start_time`` == Dateibeginn — ein gekappter Eintrag, der mit dem
       AKTUELLEN Puffer einen anderen Beginn bekäme (Puffer seither geändert).
       Ohne diesen Schritt entstünde ein zweiter Eintrag neben dem alten;
    3. ``start_time`` == Dateibeginn — ein ungekappt gespeicherter Eintrag
       (anerkannt, oder erfasst, als der Tag noch keine Blöcke hatte).

    F-026: ``tenant_id``-Filter zusätzlich zu RLS (Spec 7.3)."""
    base = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.tenant_id == tenant_id,
        TimeEntry.date == d,
    )
    for start in dict.fromkeys(s for s in starts if s is not None):
        hit = base.filter(TimeEntry.start_time == start).first()
        if hit is not None:
            return hit
    hit = base.filter(TimeEntry.raw_start_time == raw_start).first()
    if hit is not None:
        return hit
    return base.filter(TimeEntry.start_time == raw_start).first()


def _start_taken(db: Session, user_id, tenant_id, d: date, start: time, exclude_id) -> bool:
    """Belegt ein ANDERER Eintrag des Tages schon diesen Beginn?
    (``uq_tenant_user_date_start`` — SQLite prüft den Index nicht.)"""
    return db.query(TimeEntry.id).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.tenant_id == tenant_id,  # F-026
        TimeEntry.date == d,
        TimeEntry.start_time == start,
        TimeEntry.id != exclude_id,
    ).first() is not None


def _kept_entries(db: Session, user_id, tenant_id, rows_by_date: dict, replaced_ids: set) -> dict:
    """Geschlossene Bestandseinträge vom ersten bis zum letzten Tag der Datei,
    die keine Zeile überschreibt — je Datum. Für Tages-Pause und §3/§4 (Tage der
    Datei) und für §5 (auch Tage dazwischen ohne Zeile). F-026: ``tenant_id``."""
    kept: dict[date, list[TimeEntry]] = {}
    for e in db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.tenant_id == tenant_id,  # F-026
        TimeEntry.date >= min(rows_by_date),
        TimeEntry.date <= max(rows_by_date),
        TimeEntry.end_time.isnot(None),
    ).order_by(TimeEntry.date, TimeEntry.start_time).all():
        if e.id not in replaced_ids:
            kept.setdefault(e.date, []).append(e)
    return kept


def _row_counts(row) -> bool:
    """Zählt die Zeile für den Tag? Datei-Zeilen mit Ende ≤ Beginn
    überspringt ``/confirm`` — sie zählen weder für Pause, §3/§4 und
    Anwesenheit noch für §5 (Gesamtreview 1.20 B4), und sie ersetzen keinen
    Bestandseintrag (``replaced_ids``, Review-Nachzug B4). Dasselbe gilt für
    Zeilen außerhalb des Beschäftigungsfensters (``row.outside``) und für die
    Zeilen eines Tages, dessen §4-Pause sie nicht tragen (``row.day_skip``,
    Gesamtreview 1.20 B11).

    Gesamtreview 1.20 (B11): maßgeblich ist die Reihenfolge der DATEI-Zeile
    (Rohstempel), nicht die gekappte Zeit — eine Zeile ganz außerhalb der Hülle
    kollabiert auf Beginn = Ende (0 h) und zählt trotzdem, wie an jedem anderen
    Schreibweg (``work_window_service._clamp_core``)."""
    return (
        getattr(row, "outside", None) is None
        and getattr(row, "day_skip", None) is None
        and row.file_end > row.file_start
    )


def _rest_reference(db: Session, user_id, tenant_id, rows: list, kept_by_date: dict,
                    rows_by_date: dict) -> tuple[dict, dict, dict]:
    """§5 je Tag der Datei wie ``rest_time_service``: (Ende des letzten
    Arbeitstags davor bzw. ``None``, erster Beginn des Tages bzw. ``None``,
    Ruhezeit zum nächsten Arbeitstag ohne gültige Zeile).

    Arbeitstage = stehender Bestand plus Zeilen der Datei; vor dem ersten Tag der
    Datei der letzte Arbeitstag des Bestands, nach dem letzten der erste. Ende =
    ``presence_end`` (Rohstempel, beim automatisch geschlossenen Eintrag das
    wirksame Ende — P18), Beginn = Rohstempel, sonst der wirksame Wert (Spec
    7.3). Nur Zeilen, die zählen (``_row_counts``) — eine übersprungene Zeile
    setzt weder Beginn noch Ende.

    Gesamtreview 1.20 (B4): bis hierher verglich die Vorschau jede Zeile mit der
    Vorzeile — beim geteilten Dienst also die Pause mit der Ruhezeit („§5 …
    2.0h"), und ein Bestandseintrag am Abend davor, der nicht in der Datei stand,
    zählte nicht.

    Review-Nachzug B4: ein Arbeitstag, den nur der Bestand trägt (keine gültige
    Zeile — im Zeitraum der Datei oder der erste danach), prüft keine Zeile. Folgt
    er auf einen Tag mit gültigen Zeilen, meldet dieser die Ruhezeit bis zu seinem
    ersten Beginn (dritter Rückgabewert: Tag → (Arbeitsende, nächster Beginn)) —
    sonst übersähe die Vorschau einen Verstoß, den erst der Import erzeugt und den
    ``rest_time_service`` danach meldet."""
    day_end: dict[date, time] = {}
    day_start: dict[date, time] = {}

    def _end(d: date, t: Optional[time]) -> None:
        if t is not None and (d not in day_end or t > day_end[d]):
            day_end[d] = t

    def _start(d: date, t: Optional[time]) -> None:
        if t is not None and (d not in day_start or t < day_start[d]):
            day_start[d] = t

    closed = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.tenant_id == tenant_id,  # F-026
        TimeEntry.end_time.isnot(None),
    )
    before = closed.filter(TimeEntry.date < min(rows_by_date)).order_by(TimeEntry.date.desc()).first()
    if before is not None:
        for e in closed.filter(TimeEntry.date == before.date).all():
            _end(e.date, work_window_service.presence_end(e))
    after = closed.filter(TimeEntry.date > max(rows_by_date)).order_by(TimeEntry.date).first()
    if after is not None:
        for e in closed.filter(TimeEntry.date == after.date).all():
            _end(e.date, work_window_service.presence_end(e))
            _start(e.date, e.raw_start_time or e.start_time)
    for d, kept in kept_by_date.items():
        for e in kept:
            _end(d, work_window_service.presence_end(e))
            _start(d, e.raw_start_time or e.start_time)
    counted: set[date] = set()
    for row in rows:
        if _row_counts(row):
            counted.add(row.date)
            _end(row.date, row.r.raw_end or row.r.eff_end)
            _start(row.date, row.r.raw_start or row.r.eff_start)

    worked = sorted(day_end)
    reference: dict[date, Optional[datetime]] = {}
    for d in rows_by_date:
        k = bisect_left(worked, d)
        reference[d] = datetime.combine(worked[k - 1], day_end[worked[k - 1]]) if k else None
    following: dict[date, tuple[datetime, datetime]] = {}
    for prev, nxt in zip(worked, worked[1:]):
        if prev in counted and nxt not in counted and nxt in day_start:
            following[prev] = (
                datetime.combine(prev, day_end[prev]), datetime.combine(nxt, day_start[nxt]),
            )
    return reference, {d: day_start.get(d) for d in rows_by_date}, following


def parse_xls(
    file_bytes: bytes,
    user_id: uuid.UUID,
    db: Session,
    *,
    tenant_id: Optional[uuid.UUID] = None,
) -> list[ImportedEntry]:
    """
    Parst eine TimeRec-XLS-Datei und gibt ImportedEntry-Liste zurück.
    Ermittelt Konflikte (user_id+date+start_time) und ArbZG-Warnungen.

    ``tenant_id``: F-026 — der Router übergibt den Mandanten der Verwaltung.

    Raises ValueError bei ungültigem Format oder fehlenden Daten.
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError("Datei zu groß (max. 5 MB)")

    try:
        # Security review 2026-10-28: a 5.6 KB .xls with 8 padded sheets took
        # 1.26 GB. on_demand loads only the sheet we read; ragged_rows drops the
        # padding to the widest row (short rows read as empty, _cell below).
        wb = xlrd.open_workbook(file_contents=file_bytes, on_demand=True, ragged_rows=True)
    except Exception as e:  # noqa: BLE001
        # Release-Review 1.20.1: abgeschnittene/beschaedigte OLE2-Dateien
        # werfen nicht nur XLRDError, sondern z. B. CompDocError/IndexError
        # -> sonst HTTP 500. Jede Oeffnungs-Panne ist eine 400.
        raise ValueError(
            "Datei konnte nicht geöffnet werden – Datei beschädigt oder unvollständig."
        ) from e

    if "Zeiterfassung" not in wb.sheet_names():
        raise ValueError(
            f"Sheet 'Zeiterfassung' nicht gefunden. "
            f"Vorhandene Sheets: {', '.join(wb.sheet_names())}"
        )

    # §18-Bypass und §6 Abs. 2: User-Flags einmalig laden
    user_query = db.query(User).filter(User.id == user_id)
    if tenant_id is not None:
        user_query = user_query.filter(User.tenant_id == tenant_id)  # F-026
    user = user_query.first()
    if user is None:
        raise ValueError("Benutzer nicht gefunden")
    exempt = bool(getattr(user, "exempt_from_arbzg", False))
    is_night_worker = bool(getattr(user, "is_night_worker", False))
    user_tenant = user.tenant_id

    # Puffer des Mandanten (Default 15 min) — für NEUE Einträge (E80).
    grace = work_window_service.get_grace_minutes(db, user_tenant)

    try:
        ws = wb.sheet_by_name("Zeiterfassung")
    except Exception as e:  # noqa: BLE001 — on_demand: the sheet is parsed only now
        raise ValueError(
            "Datei konnte nicht geöffnet werden – Datei beschädigt oder unvollständig."
        ) from e
    finally:
        wb.release_resources()
    rows = _read_rows(ws, db, user, user_id, user_tenant, grace)
    if not rows:
        raise ValueError("Keine Datenzeilen im Sheet 'Zeiterfassung' gefunden")

    entries: list[ImportedEntry] = []

    # Spec 8.3 (PR2): Anwesenheit laut Stempel je Kalenderwoche (Tag und Woche,
    # P22) — Bestand + bisherige Zeilen der Datei.
    db_presence_by_week: dict[date, list] = {}
    batch_presence_by_week: dict[date, list] = {}
    # Review Focus 4: Bestandseinträge, die eine Zeile der Datei überschreibt,
    # zählen weder in der harten §3/§4-Aggregation noch in der Anwesenheit —
    # sonst stünde der Tag doppelt da (§3 „16.0h" neben „Angerechnet 8:00 h").
    # Gesamtreview 1.20 (B4): VOR der Bewertung der ersten Zeile vollständig —
    # sonst zählte eine frühere Zeile des Tages den Eintrag noch mit, den erst
    # eine spätere Zeile derselben Datei überschreibt. Nur Zeilen, die zählen
    # (``_row_counts``): eine Zeile mit Ende ≤ Beginn überspringt /confirm, bevor
    # sie einen Eintrag sucht — der getroffene Bestand bleibt stehen, auch mit
    # „überschreiben" (Review-Nachzug B4).
    # Gesamtreview 1.20 (B11): kann ein Tag die §4-Pause mit den Zeilen der
    # Datei nicht tragen (Rest nach der Automatik-Pause), übernimmt /confirm ihn
    # nicht — seine Zeilen zählen danach nicht mehr (``_row_counts``), ersetzen
    # also auch keinen Bestand. Deshalb ein zweiter Durchgang mit derselben
    # Rechnung, sobald ein Tag herausfällt (ein übersprungener Tag hat keine
    # gültige Zeile mehr, ein dritter Durchgang ändert nichts).
    while True:
        replaced_ids = {
            row.existing.id for row in rows if row.existing is not None and _row_counts(row)
        }

        # Gesamtreview 1.20 (B4): Pause, §3/§4 und §5 je TAG (#499) — die Zeilen
        # eines Tages und der Bestand, der stehen bleibt.
        rows_by_date: dict[date, list[int]] = {}
        for i, row in enumerate(rows):
            rows_by_date.setdefault(row.date, []).append(i)
        kept_by_date = _kept_entries(db, user_id, user_tenant, rows_by_date, replaced_ids)
        kept_blocks = {
            d: [break_block_for_entry(db, user, e) for e in kept_by_date.get(d, [])]
            for d in rows_by_date
        }
        # Zeilen mit Ende ≤ Beginn überspringt /confirm — sie zählen für den Tag nicht.
        valid_by_date = {
            d: [i for i in idxs if _row_counts(rows[i])] for d, idxs in rows_by_date.items()
        }
        newly_skipped = False
        for d, valid in valid_by_date.items():
            for i in rows_by_date[d]:
                rows[i].break_min = 0
            day_rows = [(rows[i].r.eff_start, rows[i].r.eff_end, rows[i].segs) for i in valid]
            day_breaks = _day_break_minutes(day_rows, kept_blocks[d])
            for i, b in zip(valid, day_breaks):
                rows[i].break_min = b
            if exempt or not valid:
                continue
            missing = _day_break_shortfall(
                [(*day_rows[k], day_breaks[k]) for k in range(len(valid))], kept_blocks[d],
            )
            if missing:
                reason = break_shortfall_skip_reason(missing)
                for i in valid:
                    rows[i].day_skip = reason
                    rows[i].break_min = 0
                newly_skipped = True
        if not newly_skipped:
            break
    rest_ref, day_first_start, rest_next = _rest_reference(
        db, user_id, user_tenant, rows, kept_by_date, rows_by_date,
    )
    # Ansicht jeder Zeile mit ihrer Tages-Pause für die Anwesenheits-Hinweise —
    # vorab, damit die Tagesprüfung alle Zeilen des Tages sieht. Netto wie
    # TimeEntry.net_hours (E13, Spec 7.4) — dieselbe Formel, die der Import speichert.
    views = [
        SimpleNamespace(
            date=row.date, start_time=row.r.eff_start, end_time=row.r.eff_end,
            raw_start_time=row.r.raw_start, raw_end_time=row.r.raw_end,
            break_minutes=row.break_min, auto_closed=False,
            uncredited_minutes=row.r.uncredited_minutes,
            net_hours=float(TimeEntry(
                start_time=row.r.eff_start, end_time=row.r.eff_end,
                break_minutes=row.break_min, uncredited_minutes=row.r.uncredited_minutes,
            ).net_hours),
        )
        for row in rows
    ]

    for i, row in enumerate(rows):
        entry_date, note = row.date, row.note
        r, segs, existing, override = row.r, row.segs, row.existing, row.override
        start_t, end_t = r.eff_start, r.eff_end
        raw_start_t, raw_end_t = r.raw_start, r.raw_end
        break_min = row.break_min
        net = views[i].net_hours

        # Außerhalb des Beschäftigungsfensters: ``/confirm`` überspringt die
        # Zeile — die Vorschau sagt das, und nur das (jede weitere Meldung gälte
        # einem Eintrag, den es nie geben wird). Sie zählt für keinen Tag und
        # trifft keinen Bestand (``_read_rows``: ``existing`` None).
        skip_reason = row.outside if row.outside is not None else getattr(row, "day_skip", None)
        if skip_reason is not None:
            entries.append(ImportedEntry(
                date=entry_date,
                start_time=start_t,
                end_time=end_t,
                break_minutes=break_min,
                note=note,
                has_conflict=False,
                arbzg_warnings=[f"Wird übersprungen — {skip_reason}."],
                raw_start_time=raw_start_t,
                raw_end_time=raw_end_t,
                uncredited_minutes=r.uncredited_minutes,
                net_hours=net,
            ))
            continue

        # §3/§4 einmal je Tag, an seiner letzten (gültigen) Zeile: alle Zeilen
        # des Tages mit ihrer Tages-Pause plus der stehende Bestand. §5 einmal je
        # Tag, an seiner ersten gültigen Zeile: Ende des letzten Arbeitstags davor
        # gegen den ersten Beginn des Tages (Rohstempel, Spec 7.3) — nie gegen die
        # Vorzeile desselben Tages (geteilter Dienst = Pause, keine Ruhezeit). Die
        # Ruhezeit bis zu einem Folgetag, den nur der Bestand trägt, an der
        # letzten gültigen Zeile (Review-Nachzug B4).
        valid = valid_by_date[entry_date]
        day_check = bool(valid) and i == valid[-1]
        other_blocks = []
        if day_check:
            other_blocks = kept_blocks[entry_date] + [
                break_block_for_new(rows[j].r.eff_start, rows[j].r.eff_end,
                                    rows[j].break_min, rows[j].segs)
                for j in valid if j != i
            ]
        first_of_day = bool(valid) and i == valid[0]

        arbzg_warnings = _check_arbzg(
            entry_date, start_t, end_t, break_min,
            rest_ref[entry_date] if first_of_day else None,
            exempt=exempt, is_night_worker=is_night_worker,
            same_day_blocks=other_blocks or None,
            uncredited_segments=segs,
            rest_start=day_first_start[entry_date],
            check_day=day_check,
            next_rest=rest_next.get(entry_date) if day_check else None,
        )
        # P14: §4 auf angerechneter Zeit „bestanden" = keine §4-Meldung der Vorschau.
        break_passed = not any(w.startswith("§4 ArbZG") for w in arbzg_warnings)

        # #462: Die Kappung darf auch hier nicht stumm passieren. Spec 7.1 Nr. 11:
        # auch ein reiner Lückenfall (K1, ohne raw_*) bekommt den Hinweis.
        # Klartext ohne Code-Präfix (Tooltip der Vorschau).
        if raw_start_t is not None or raw_end_t is not None or r.uncredited_minutes > 0:
            clamp_note = work_window_service.clamp_warning_text(
                db, user, entry_date, r, for_employee=False,
            )
            if clamp_note:
                arbzg_warnings = arbzg_warnings + [clamp_note]
        # Eine übersprungene Zeile ersetzt den anerkannten Eintrag nicht.
        if override and _row_counts(row):
            arbzg_warnings = arbzg_warnings + [CREDIT_OVERRIDE_IMPORT_NOTE]

        # Spec 8.3: weiche Anwesenheits-Hinweise (Tag, Woche) als Klartext ohne
        # Code — dieselben Regeln wie in den Schreibpfaden
        # (presence_service.presence_hints). §18 → keine.
        # KEIN ``BREAK_IN_GAP`` (Eintrag ``None``): die Auto-Pause der Vorschau
        # ist nach E45 / 8.4 Zeile 1 schon die Maßnahme gegen den Doppelabzug —
        # sie trägt nur den §4-Rest, den die Lückensegmente nicht decken (7.4).
        # „Bitte die Pause auf 0 setzen" wäre hier falsch (§4-Verstoß) und in
        # der Vorschau ohnehin nicht umsetzbar (/confirm rechnet die Pause neu).
        # Die Tages-Hinweise gelten dem Tag wie §3/§4: einmal an dessen letzter
        # gültiger Zeile, über den stehenden Bestand plus ALLE gültigen Zeilen
        # mit ihrer Tages-Pause; an den übrigen Zeilen kein Tag (``[]``). Bis
        # zum Review-Nachzug B4 je Zeile über den bis dahin gelesenen Teil des
        # Tages — eine frühere Zeile meldete eine fehlende Ruhepause, die erst
        # eine spätere Zeile des Tages trägt. Der Wochenhinweis bleibt
        # schrittweise (Bestand + bisherige Zeilen).
        if not exempt:
            own_view = [views[i]] if _row_counts(row) else []
            monday = entry_date - timedelta(days=entry_date.weekday())
            if monday not in db_presence_by_week:
                db_presence_by_week[monday] = presence_service.closed_entries(
                    db, user, monday, monday + timedelta(days=6),
                )
            week_rows = (
                [e for e in db_presence_by_week[monday] if e.id not in replaced_ids]
                + batch_presence_by_week.get(monday, [])
                + own_view
            )
            day_rows = (
                kept_by_date.get(entry_date, []) + [views[j] for j in valid]
                if day_check else []
            )
            hints = presence_service.presence_hints(
                None, day_rows, week_rows, break_check_passed=break_passed,
            )
            arbzg_warnings = arbzg_warnings + [presence_service.plain_text(h) for h in hints]
            batch_presence_by_week.setdefault(monday, []).extend(own_view)

        entries.append(ImportedEntry(
            date=entry_date,
            start_time=start_t,
            end_time=end_t,
            break_minutes=break_min,
            note=note,
            has_conflict=existing is not None,
            arbzg_warnings=arbzg_warnings,
            raw_start_time=raw_start_t,
            raw_end_time=raw_end_t,
            uncredited_minutes=r.uncredited_minutes,
            net_hours=net,
        ))

    return entries


def _cell(ws, row_idx: int, col: int):
    """Cell of a ``ragged_rows`` sheet; past the end of a short row it reads
    as the empty cell the padded layout used to hold."""
    if col >= ws.row_len(row_idx):
        return xlrd.sheet.empty_cell
    return ws.cell(row_idx, col)


def _read_rows(ws, db: Session, user, user_id, user_tenant, grace: int) -> list:
    """Erster Durchgang der Vorschau: Datenzeilen lesen, kappen und den
    Bestandseintrag suchen, den die Zeile überschreiben würde.

    Gesamtreview 1.20 (B4): getrennt von der Bewertung, damit die Menge der
    überschriebenen Einträge (und die Zeilen eines Tages) schon vor der ersten
    Prüfung feststeht."""
    rows = []
    for row_idx in range(ws.nrows):
        # Datenzeile erkennbar durch numerischen ctype (3) in Ein-Spalte (D)
        if _cell(ws, row_idx, 3).ctype != 3:
            continue

        ein_serial = _cell(ws, row_idx, 3).value
        aus_serial = _cell(ws, row_idx, 4).value
        notiz_raw = _cell(ws, row_idx, 5).value

        ein_dt = _excel_serial_to_datetime(ein_serial)
        aus_dt = _excel_serial_to_datetime(aus_serial)
        note = str(notiz_raw).strip() if notiz_raw is not None and str(notiz_raw).strip() else None

        entry_date = ein_dt.date()
        # Sekunden auf 0 setzen (XLS hat keine Sekunden)
        file_start = ein_dt.time().replace(second=0, microsecond=0)
        file_end = aus_dt.time().replace(second=0, microsecond=0)

        # Spec 6.1/E80: neue Zeilen kappen mit dem aktuellen Puffer; trifft die
        # Zeile einen GESPEICHERTEN Eintrag, gelten dessen Puffer und dessen
        # Anerkennung (P3) — die Vorschau zeigt, was /confirm schreiben wird.
        r, segs = work_window_service.clamp_with_segments(
            db, user, entry_date, file_start, file_end, grace, credit_override=False,
        )
        # Außerhalb des Beschäftigungsfensters oder in der Zukunft (Ultrareview
        # 1.20, Fund 2) überspringt ``/confirm`` die Zeile,
        # bevor sie einen Eintrag sucht — sie ersetzt also auch keinen.
        outside = import_skip_reason(user, entry_date)
        existing = None if outside is not None else _find_existing_entry(
            db, user_id, user_tenant, entry_date, starts=(r.eff_start,), raw_start=file_start,
        )
        override = bool(existing is not None and existing.credit_override)
        row_grace = (
            work_window_service.grace_for_entry(db, existing) if existing is not None else grace
        )
        # Ultrareview 1.20: Segmente aus demselben Lauf wie ``r`` — neu gekappt
        # nur, wenn Puffer oder Anerkennung des gespeicherten Eintrags abweichen.
        if override or row_grace != grace:
            r, segs = work_window_service.clamp_with_segments(
                db, user, entry_date, file_start, file_end, row_grace, credit_override=override,
            )
        rows.append(SimpleNamespace(
            date=entry_date, note=note, r=r, segs=segs, existing=existing, override=override,
            outside=outside, file_start=file_start, file_end=file_end,
        ))
    return rows



def _apply_day_breaks(db: Session, user, user_id, tenant_id, day: date,
                      written: dict, logs: list, *, exempt: bool = False) -> tuple[list[str], int]:
    """``/confirm``: Tages-Pause der an ``day`` geschriebenen Einträge setzen und
    deren Protokollzeilen anlegen (Gesamtreview 1.20 B4).

    ``written`` = Eintrags-ID → (Eintrag, Lückensegmente, Pause der Vorschau) in
    Schreibreihenfolge, ``logs`` = (Protokollzeile, Eintrag). Mitgerechnet wird
    der Bestand des Tages, den der Import nicht angefasst hat — auch ein
    Konflikt, der ohne „überschreiben" stehen bleibt. Dieselbe Regel wie die
    Vorschau (``_day_break_minutes``). Die Protokollzeilen entstehen erst hier,
    weil ``new_break_minutes`` in den Manipulationsschutz ``row_hash`` (#121)
    eingeht.

    Rückgabe: (Ergebnis-Hinweise je Eintrag, dessen Pause von der Vorschau
    abweicht; §4-Fehlbetrag in Minuten). Die Vorschau rechnet jeden Konflikt als
    überschrieben; ohne „überschreiben" bleibt der Bestand stehen und zählt hier
    mit — die Pause ändert sich dann, ohne dass es jemand sähe (Review-Nachzug
    B4). Ebenso nach einer Zwischenänderung oder bei einer doppelten Zeile der
    Datei.

    Gesamtreview 1.20 (B11): bleibt nach der Automatik-Pause ein §4-Fehlbetrag
    (``_day_break_shortfall``, außer bei §18-Befreiung), setzt die Funktion
    nichts und legt keine Protokollzeile an — der Aufrufer nimmt den Tag dann
    zurück (``_undo_day``)."""
    kept = [
        break_block_for_entry(db, user, e)
        for e in db.query(TimeEntry).filter(
            TimeEntry.user_id == user_id,
            TimeEntry.tenant_id == tenant_id,  # F-026
            TimeEntry.date == day,
        ).all()
        if e.end_time is not None and e.id not in written
    ]
    items = list(written.values())
    day_rows = [(e.start_time, e.end_time, segs) for e, segs, _ in items]
    breaks = _day_break_minutes(day_rows, kept)
    if not exempt:
        missing = _day_break_shortfall(
            [(*row, b) for row, b in zip(day_rows, breaks)], kept,
        )
        if missing:
            return [], missing
    notes = []
    for (e, _, shown), minutes in zip(items, breaks):
        e.break_minutes = minutes
        if minutes != shown:
            notes.append(
                f"{day.strftime('%d.%m.%Y')} {e.start_time.strftime('%H:%M')}: "
                f"Pause an den Tag angepasst ({shown} → {minutes} Min) – Einträge, die "
                f"stehen bleiben (z. B. nicht überschriebene Konflikte), zählen für die "
                f"Tagespause mit."
            )
    for log, e in logs:
        log.new_break_minutes = e.break_minutes
        db.add(log)
    return notes, 0


# Spalten, die ``/confirm`` an einem überschriebenen Eintrag setzt — für die
# Rücknahme eines Tages (``_undo_day``).
_OVERWRITE_FIELDS = (
    "start_time", "end_time", "note", "raw_start_time", "raw_end_time",
    "uncredited_minutes", "clamp_grace_minutes", "auto_closed", "break_minutes",
)


def _undo_day(db: Session, undo: list) -> None:
    """Nimmt die Schreibschritte eines Tages zurück (Gesamtreview 1.20 B11) —
    in umgekehrter Reihenfolge: ``("new", entry)`` wird gelöscht,
    ``("overwrite", entry, snapshot)`` bekommt seine alten Werte zurück. Jeder
    Schritt wird sofort geflusht (``uq_tenant_user_date_start`` ist nicht
    verzögerbar; ein gemeinsamer Flush ordnete UPDATE vor DELETE). Protokollzeilen
    gibt es zu diesem Zeitpunkt noch keine (``_apply_day_breaks``)."""
    for step in reversed(undo):
        if step[0] == "new":
            db.delete(step[1])
        else:
            _, entry, snapshot = step
            for field, value in snapshot.items():
                setattr(entry, field, value)
        db.flush()


def execute_import(
    user_id: uuid.UUID,
    entries: Sequence[ImportedEntryIn],
    overwrite: bool,
    db: Session,
    changed_by_id: uuid.UUID,
    filename: str,
    tenant_id: uuid.UUID | None = None,
) -> ImportResult:
    """
    Führt den Import durch. Bei overwrite=True werden Konflikte überschrieben,
    sonst übersprungen. Schreibt Audit-Log-Einträge.

    F-042: Fully wrapped in try/except. On any failure the whole batch
    rolls back (so the DB can't end up with half-imported rows) and a
    separate audit-log transaction is written to record the failure.
    """
    try:
        return _execute_import_inner(
            user_id=user_id,
            entries=entries,
            overwrite=overwrite,
            db=db,
            changed_by_id=changed_by_id,
            filename=filename,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        db.rollback()
        # Write a standalone failure audit log in a fresh transaction.
        try:
            failure_log = TimeEntryAuditLog(
                time_entry_id=None,
                user_id=user_id,
                changed_by=changed_by_id,
                action="import",
                source="import",
                new_note=(
                    f"XLS-Import FEHLGESCHLAGEN | Benutzer: {user_id} "
                    f"| Datei: {filename} | Fehler: {type(exc).__name__}: {exc}"[:1000]
                ),
                tenant_id=tenant_id,
            )
            db.add(failure_log)
            db.commit()
        except Exception:
            db.rollback()
        # Re-raise as ValueError so the router translates to HTTP 400 cleanly
        raise ValueError(f"Import fehlgeschlagen: {exc}") from exc


def _execute_import_inner(
    user_id: uuid.UUID,
    entries: Sequence[ImportedEntryIn],
    overwrite: bool,
    db: Session,
    changed_by_id: uuid.UUID,
    filename: str,
    tenant_id: uuid.UUID | None = None,
) -> ImportResult:
    """Actual import body. Callers should use execute_import() which wraps it."""
    # Lokaler Import: ein Service greift auf den Router-Helfer zu (kein Zirkel
    # beim Laden von app.routers).
    from app.routers.admin_helpers import lock_user_row

    imported = 0
    skipped = 0
    overwritten = 0
    all_warnings: list[str] = []

    # Spec P5: Ankersperre der Zielperson EINMAL am Anfang — vor Puffer,
    # Snapshot-Auflösung und clamp, vor jeder Zeilensperre.
    lock_user_row(db, tenant_id, user_id)

    # Einmal fuer die Schleife: Ziel-Person (fuer die Kappung unten und die
    # Zusammenfassung am Ende) und der Tenant-Puffer.
    target_query = db.query(User).filter(User.id == user_id)
    if tenant_id is not None:
        target_query = target_query.filter(User.tenant_id == tenant_id)  # F-026
    target_user = target_query.first()
    grace = work_window_service.get_grace_minutes(db, tenant_id)

    # Gesamtreview 1.20 (B4): die Automatik-Pause gilt dem TAG (#499) — erst alle
    # Zeilen eines Tages schreiben, dann die Pause über die geschriebenen Zeilen
    # plus den stehenden Bestand rechnen (``_apply_day_breaks``), mit derselben
    # Regel wie die Vorschau. Tage in der Reihenfolge ihrer ersten Zeile,
    # innerhalb des Tages die Reihenfolge der Datei.
    by_date: dict[date, list] = {}
    for entry in entries:
        by_date.setdefault(entry.date, []).append(entry)

    for day, day_entries in by_date.items():
        # Eintrags-ID → (Eintrag, Lückensegmente, Pause der Vorschau) in
        # Schreibreihenfolge; die Protokollzeilen entstehen erst mit der
        # Tages-Pause (``new_break_minutes``).
        written: dict = {}
        logs: list = []
        # Gesamtreview 1.20 (B11): Schreibschritte, Zähler und Hinweise des Tages
        # erst nach der Tages-Pause übernehmen — fehlt dann noch §4-Pause, nimmt
        # ``_undo_day`` den Tag zurück.
        undo: list = []
        day_imported = day_overwritten = 0
        day_warnings: list[str] = []
        for entry in day_entries:
            # Gesamtreview 1.20: außerhalb des Beschäftigungsfensters der
            # Zielperson sichtbar überspringen (``employment_window_skip_reason``)
            # — vor der Eintragssuche, die Zeile ersetzt also auch mit
            # „überschreiben" keinen Bestand. Server-seitig, /confirm nimmt die
            # Zeilen vom Client; der Hinweis der Vorschau wird nicht übernommen.
            # Ultrareview 1.20 (Fund 2): ebenso ein Datum in der Zukunft.
            outside = import_skip_reason(target_user, entry.date)
            if outside is not None:
                skipped += 1
                all_warnings.append(
                    f"{entry.date.strftime('%d.%m.%Y')}: übersprungen — {outside}."
                )
                continue
            # Release-Review 1.19.1 + Spec 7.4: NICHT den Client-Werten vertrauen.
            # /confirm nimmt die Einträge aus dem Request-Body entgegen; wo gekappt
            # wird, rechnet der Server Zeiten, raw_* und uncredited neu, und zwar
            # aus dem Rohwert (für eine unveränderte Vorschau identisch). Die
            # Auto-Pause rechnet er immer selbst (je Tag, ``_apply_day_breaks``).
            file_start = entry.raw_start_time or entry.start_time
            file_end = entry.raw_end_time or entry.end_time

            # Invariant end_time > start_time. net_hours floors a negative duration
            # to 0, so an end<=start row (over-midnight shift, or corrupt/forged
            # source — /confirm trusts client-supplied entries) would otherwise be
            # stored as a phantom 0h entry: wrong pay + it bypasses the §3 daily cap.
            # The interactive write paths reject this; the importer must too. Skip it
            # with a visible warning (over-midnight shifts are entered as two entries).
            # Gesamtreview 1.20 (B11): geprüft wird die DATEI-Zeile (Rohstempel),
            # nicht die gekappte Zeit der Vorschau — eine Zeile ganz außerhalb der
            # Hülle (18:00–20:00 bei Block 08–12) kollabiert auf 18:00–18:00 und
            # wird wie an jedem anderen Schreibweg mit 0 h angelegt, Rohstempel
            # erhalten (§16), statt mit „Endzeit (18:00) liegt nicht nach
            # Startzeit (18:00)" verloren zu gehen.
            if file_end is None or file_end <= file_start:
                skipped += 1
                all_warnings.append(
                    f"{entry.date.strftime('%d.%m.%Y')}: übersprungen — Endzeit "
                    f"({file_end.strftime('%H:%M') if file_end else '—'}) "
                    f"liegt nicht nach Startzeit ({file_start.strftime('%H:%M')}). "
                    f"Über-Mitternacht-Schichten als zwei Einträge erfassen."
                )
                continue
            first, first_segs = work_window_service.clamp_with_segments(
                db, target_user, entry.date, file_start, file_end, grace, credit_override=False,
            )
            # ``has_conflict`` der Vorschau ist nur ein Stand: zwischen Vorschau und
            # Bestätigung kann ein Eintrag entstanden sein — deshalb hier neu suchen.
            existing = _find_existing_entry(
                db, user_id, tenant_id, entry.date,
                starts=(first.eff_start, entry.start_time), raw_start=file_start,
            )
            override = bool(existing is not None and existing.credit_override)
            row_grace = (
                work_window_service.grace_for_entry(db, existing) if existing is not None else grace
            )
            # E38: ``clamp_applies`` statt „hat Blöcke" — prüft zusätzlich
            # track_hours und credit_override. Ohne Kappung bleibt ein mitgeliefertes
            # raw_* als §16-Nachweis stehen, statt von einer Kappung gelöscht zu
            # werden, die gar nicht stattfindet.
            if target_user is not None and work_window_service.clamp_applies(
                db, target_user, entry.date, credit_override=override,
            ):
                # Ultrareview 1.20: dieselben Eingaben wie ``first`` (gleicher
                # Puffer) → dessen Lauf wiederverwenden statt erneut zu kappen.
                if row_grace == grace:
                    r, segs = first, first_segs
                else:
                    r, segs = work_window_service.clamp_with_segments(
                        db, target_user, entry.date, file_start, file_end, row_grace,
                        credit_override=False,
                    )
                eff_start, eff_end, raw_start, raw_end = r.eff_start, r.eff_end, r.raw_start, r.raw_end
                uncredited, applied_grace = r.uncredited_minutes, r.grace_minutes
            elif entry.end_time is None or entry.end_time <= entry.start_time:
                # Gesamtreview 1.20 (B11-Nachzug): ohne Kappung gilt die
                # Invariante Ende > Beginn auch für die mitgeschickten Zeiten.
                # Eine veraltete Kollaps-Vorschau (18:00–18:00 aus Blöcken, die
                # jetzt nicht mehr kappen) oder eine gefälschte Zeile folgt der
                # Datei-Zeile — geprüft oben, Ende nach Beginn.
                eff_start, eff_end = file_start, file_end
                raw_start, raw_end = None, None
                uncredited, applied_grace = 0, None
                segs = []
            else:
                eff_start, eff_end = entry.start_time, entry.end_time
                raw_start, raw_end = entry.raw_start_time, entry.raw_end_time
                uncredited, applied_grace = 0, None
                # Spec 7.4: die Pause kommt nie vom Client — auch ohne Kappung
                # rechnet der Server sie (je Tag, unten).
                segs = []

            for w in entry.arbzg_warnings:
                day_warnings.append(f"{entry.date.strftime('%d.%m.%Y')}: {w}")

            if existing:
                if not overwrite:
                    skipped += 1
                    continue
                if eff_start != existing.start_time and _start_taken(
                    db, user_id, tenant_id, entry.date, eff_start, existing.id,
                ):
                    skipped += 1
                    all_warnings.append(
                        f"{entry.date.strftime('%d.%m.%Y')}: übersprungen — ein anderer "
                        f"Eintrag beginnt bereits um {eff_start.strftime('%H:%M')}."
                    )
                    continue

                undo.append(("overwrite", existing, {
                    f: getattr(existing, f) for f in _OVERWRITE_FIELDS
                }))
                # Audit-Log: alter Zustand
                log = TimeEntryAuditLog(
                    time_entry_id=existing.id,
                    user_id=user_id,
                    changed_by=changed_by_id,
                    action="update",
                    source="import",
                    old_date=existing.date,
                    old_start_time=existing.start_time,
                    old_end_time=existing.end_time,
                    old_break_minutes=existing.break_minutes,
                    old_note=existing.note,
                    new_date=entry.date,
                    new_start_time=eff_start,
                    new_end_time=eff_end,
                    new_note=entry.note,
                    tenant_id=tenant_id,
                )
                existing.start_time = eff_start
                existing.end_time = eff_end
                existing.note = entry.note
                # Audit R3/§16: Roh-Stempel des Import-Eintrags übernehmen, sonst
                # geht der Nachweis der tatsächlichen Anwesenheit beim Overwrite
                # verloren (gekappter Wert bliebe, Rohwert verschwände).
                existing.raw_start_time = raw_start
                existing.raw_end_time = raw_end
                existing.uncredited_minutes = uncredited
                if applied_grace is not None:
                    existing.clamp_grace_minutes = applied_grace
                # P18: der Import liefert ein echtes Ende; credit_override bleibt (P3).
                existing.auto_closed = False
                target = existing
                day_overwritten += 1
            else:
                new_entry = TimeEntry(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    date=entry.date,
                    start_time=eff_start,
                    end_time=eff_end,
                    break_minutes=0,  # Tages-Pause folgt in ``_apply_day_breaks``
                    note=entry.note,
                    raw_start_time=raw_start,
                    raw_end_time=raw_end,
                    uncredited_minutes=uncredited,
                    clamp_grace_minutes=applied_grace,
                )
                db.add(new_entry)
                db.flush()  # ID für Audit-Log
                undo.append(("new", new_entry))

                log = TimeEntryAuditLog(
                    time_entry_id=new_entry.id,
                    user_id=user_id,
                    changed_by=changed_by_id,
                    action="create",
                    source="import",
                    new_date=entry.date,
                    new_start_time=eff_start,
                    new_end_time=eff_end,
                    new_note=entry.note,
                    tenant_id=tenant_id,
                )
                target = new_entry
                day_imported += 1

            # Eine doppelte Zeile der Datei überschreibt den eben angelegten Eintrag
            # — er zählt für den Tag nur einmal, an der späteren Stelle.
            written.pop(target.id, None)
            written[target.id] = (target, segs, entry.break_minutes)
            logs.append((log, target))

        if written:
            notes, missing = _apply_day_breaks(
                db, target_user, user_id, tenant_id, day, written, logs,
                exempt=bool(getattr(target_user, "exempt_from_arbzg", False)),
            )
            if missing:
                # Der Tag bleibt, wie er war: keine der Zeilen wird übernommen,
                # ihre Vorschau-Hinweise entfallen (sie gälten Einträgen, die es
                # nicht gibt).
                _undo_day(db, undo)
                skipped += day_imported + day_overwritten
                all_warnings.append(
                    f"{day.strftime('%d.%m.%Y')}: übersprungen — "
                    f"{break_shortfall_skip_reason(missing)}."
                )
                continue
            all_warnings.extend(day_warnings)
            all_warnings.extend(notes)
            imported += day_imported
            overwritten += day_overwritten
        else:
            all_warnings.extend(day_warnings)

    # Zusammenfassungs-Eintrag im Audit-Log (action="import", time_entry_id=None)
    username = f"{target_user.first_name} {target_user.last_name}" if target_user else str(user_id)
    summary = (
        f"XLS-Import: {imported} neu, {overwritten} überschrieben, {skipped} übersprungen "
        f"| Benutzer: {username} | Datei: {filename}"
    )
    summary_log = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=user_id,
        changed_by=changed_by_id,
        action="import",
        source="import",
        new_note=summary,
        tenant_id=tenant_id,
    )
    db.add(summary_log)
    db.commit()

    return ImportResult(
        imported=imported,
        skipped=skipped,
        overwritten=overwritten,
        warnings=all_warnings,
    )
