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
    (Doppelabzug, E45). Ein Rest unter 15 Min wird auf 15 aufgerundet (§4 Satz 2).
    Der Rest steht an der längsten Zeile (bei Gleichstand an der ersten): dort
    liegt die Pause am ehesten, und eine kurze Zeile verlöre sonst den größten
    Teil ihrer Zeit.

    Gesamtreview 1.20 (B4): bis hierher je ZEILE gerechnet — ein geteilter
    Dienst aus zwei Zeilen unter 6 h bekam gar keine Pause, zwei Zeilen über 6 h
    bekamen je eine (der Abstand dazwischen zählte nicht).
    Note: assumes end > start (no overnight shifts) — TimeRec liefert keine."""
    if not rows:
        return []
    own = [break_block_for_new(s, e, 0, segs) for s, e, segs in rows]
    credited, covered = daily_break_figures(list(kept) + own)
    required = 45 if credited > 9 * 60 else 30 if credited > 6 * 60 else 0
    rest = max(0, required - covered)
    if 0 < rest < 15:
        rest = 15
    breaks = [0] * len(rows)
    if rest:
        longest = max(
            range(len(own)),
            key=lambda i: (own[i].end - own[i].start - own[i].deduct_minutes, -i),
        )
        breaks[longest] = rest
    return breaks


def _calc_break_minutes(eff_start: time, eff_end: time, segments: Sequence[int]) -> int:
    """Auto-Pause einer einzelnen Zeile ohne weitere Einträge am Tag — der
    Sonderfall von ``_day_break_minutes`` (eine Regel, kein Nachbau)."""
    return _day_break_minutes([(eff_start, eff_end, segments)])[0]


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


def _rest_reference(db: Session, user_id, tenant_id, rows: list, kept_by_date: dict,
                    rows_by_date: dict) -> tuple[dict, dict]:
    """§5 je Tag der Datei wie ``rest_time_service``: (Ende des letzten
    Arbeitstags davor bzw. ``None``, erster Beginn des Tages).

    Arbeitstage = stehender Bestand plus Zeilen der Datei; vor dem ersten Tag der
    Datei der letzte Arbeitstag des Bestands. Ende = ``presence_end``
    (Rohstempel, beim automatisch geschlossenen Eintrag das wirksame Ende — P18),
    Beginn = Rohstempel, sonst der wirksame Wert (Spec 7.3).

    Gesamtreview 1.20 (B4): bis hierher verglich die Vorschau jede Zeile mit der
    Vorzeile — beim geteilten Dienst also die Pause mit der Ruhezeit („§5 …
    2.0h"), und ein Bestandseintrag am Abend davor, der nicht in der Datei stand,
    zählte nicht."""
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
    for d, kept in kept_by_date.items():
        for e in kept:
            _end(d, work_window_service.presence_end(e))
            _start(d, e.raw_start_time or e.start_time)
    for row in rows:
        _end(row.date, row.r.raw_end or row.r.eff_end)
        _start(row.date, row.r.raw_start or row.r.eff_start)

    worked = sorted(day_end)
    reference: dict[date, Optional[datetime]] = {}
    for d in rows_by_date:
        k = bisect_left(worked, d)
        reference[d] = datetime.combine(worked[k - 1], day_end[worked[k - 1]]) if k else None
    return reference, {d: day_start[d] for d in rows_by_date}


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
        wb = xlrd.open_workbook(file_contents=file_bytes)
    except xlrd.XLRDError as e:
        raise ValueError(f"Datei konnte nicht geöffnet werden: {e}")

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

    ws = wb.sheet_by_name("Zeiterfassung")
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
    # eine spätere Zeile derselben Datei überschreibt.
    replaced_ids = {row.existing.id for row in rows if row.existing is not None}

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
        d: [i for i in idxs if rows[i].r.eff_end > rows[i].r.eff_start]
        for d, idxs in rows_by_date.items()
    }
    for d, valid in valid_by_date.items():
        for i in rows_by_date[d]:
            rows[i].break_min = 0
        day_breaks = _day_break_minutes(
            [(rows[i].r.eff_start, rows[i].r.eff_end, rows[i].segs) for i in valid],
            kept_blocks[d],
        )
        for i, b in zip(valid, day_breaks):
            rows[i].break_min = b
    rest_ref, day_first_start = _rest_reference(
        db, user_id, user_tenant, rows, kept_by_date, rows_by_date,
    )

    for i, row in enumerate(rows):
        entry_date, note = row.date, row.note
        r, segs, existing, override = row.r, row.segs, row.existing, row.override
        start_t, end_t = r.eff_start, r.eff_end
        raw_start_t, raw_end_t = r.raw_start, r.raw_end
        break_min = row.break_min

        # §3/§4 einmal je Tag, an seiner letzten (gültigen) Zeile: alle Zeilen
        # des Tages mit ihrer Tages-Pause plus der stehende Bestand. §5 einmal je
        # Tag, an seiner ersten Zeile: Ende des letzten Arbeitstags davor gegen
        # den ersten Beginn des Tages (Rohstempel, Spec 7.3) — nie gegen die
        # Vorzeile desselben Tages (geteilter Dienst = Pause, keine Ruhezeit).
        valid = valid_by_date[entry_date]
        day_check = bool(valid) and i == valid[-1]
        other_blocks = []
        if day_check:
            other_blocks = kept_blocks[entry_date] + [
                break_block_for_new(rows[j].r.eff_start, rows[j].r.eff_end,
                                    rows[j].break_min, rows[j].segs)
                for j in valid if j != i
            ]
        first_of_day = i == rows_by_date[entry_date][0]

        arbzg_warnings = _check_arbzg(
            entry_date, start_t, end_t, break_min,
            rest_ref[entry_date] if first_of_day else None,
            exempt=exempt, is_night_worker=is_night_worker,
            same_day_blocks=other_blocks or None,
            uncredited_segments=segs,
            rest_start=day_first_start[entry_date],
            check_day=day_check,
        )
        # P14: §4 auf angerechneter Zeit „bestanden" = keine §4-Meldung der Vorschau.
        break_passed = not any(w.startswith("§4 ArbZG") for w in arbzg_warnings)

        # Spec 7.4: Netto wie TimeEntry.net_hours (E13) — dieselbe Formel, die
        # der Import speichert.
        net = float(TimeEntry(
            start_time=start_t, end_time=end_t, break_minutes=break_min,
            uncredited_minutes=r.uncredited_minutes,
        ).net_hours)

        # #462: Die Kappung darf auch hier nicht stumm passieren. Spec 7.1 Nr. 11:
        # auch ein reiner Lückenfall (K1, ohne raw_*) bekommt den Hinweis.
        # Klartext ohne Code-Präfix (Tooltip der Vorschau).
        if raw_start_t is not None or raw_end_t is not None or r.uncredited_minutes > 0:
            clamp_note = work_window_service.clamp_warning_text(
                db, user, entry_date, r, for_employee=False,
            )
            if clamp_note:
                arbzg_warnings = arbzg_warnings + [clamp_note]
        if override:
            arbzg_warnings = arbzg_warnings + [CREDIT_OVERRIDE_IMPORT_NOTE]

        # Spec 8.3: weiche Anwesenheits-Hinweise (Tag, Woche) als Klartext ohne
        # Code — dieselben Regeln wie in den Schreibpfaden
        # (presence_service.presence_hints). §18 → keine.
        # KEIN ``BREAK_IN_GAP`` (Eintrag ``None``): die Auto-Pause der Vorschau
        # ist nach E45 / 8.4 Zeile 1 schon die Maßnahme gegen den Doppelabzug —
        # sie trägt nur den §4-Rest, den die Lückensegmente nicht decken (7.4).
        # „Bitte die Pause auf 0 setzen" wäre hier falsch (§4-Verstoß) und in
        # der Vorschau ohnehin nicht umsetzbar (/confirm rechnet die Pause neu).
        if not exempt:
            row_view = SimpleNamespace(
                date=entry_date, start_time=start_t, end_time=end_t,
                raw_start_time=raw_start_t, raw_end_time=raw_end_t, break_minutes=break_min,
                auto_closed=False, uncredited_minutes=r.uncredited_minutes, net_hours=net,
            )
            monday = entry_date - timedelta(days=entry_date.weekday())
            if monday not in db_presence_by_week:
                db_presence_by_week[monday] = presence_service.closed_entries(
                    db, user, monday, monday + timedelta(days=6),
                )
            week_rows = (
                [e for e in db_presence_by_week[monday] if e.id not in replaced_ids]
                + batch_presence_by_week.get(monday, [])
                + [row_view]
            )
            hints = presence_service.presence_hints(
                None, [e for e in week_rows if e.date == entry_date], week_rows,
                break_check_passed=break_passed,
            )
            arbzg_warnings = arbzg_warnings + [presence_service.plain_text(h) for h in hints]
            batch_presence_by_week.setdefault(monday, []).append(row_view)

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


def _read_rows(ws, db: Session, user, user_id, user_tenant, grace: int) -> list:
    """Erster Durchgang der Vorschau: Datenzeilen lesen, kappen und den
    Bestandseintrag suchen, den die Zeile überschreiben würde.

    Gesamtreview 1.20 (B4): getrennt von der Bewertung, damit die Menge der
    überschriebenen Einträge (und die Zeilen eines Tages) schon vor der ersten
    Prüfung feststeht."""
    rows = []
    for row_idx in range(ws.nrows):
        # Datenzeile erkennbar durch numerischen ctype (3) in Ein-Spalte (D)
        if ws.cell(row_idx, 3).ctype != 3:
            continue

        ein_serial = ws.cell_value(row_idx, 3)
        aus_serial = ws.cell_value(row_idx, 4)
        notiz_raw = ws.cell_value(row_idx, 5)

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
        r = work_window_service.clamp(
            db, user, entry_date, file_start, file_end, grace, credit_override=False,
        )
        existing = _find_existing_entry(
            db, user_id, user_tenant, entry_date, starts=(r.eff_start,), raw_start=file_start,
        )
        override = bool(existing is not None and existing.credit_override)
        row_grace = (
            work_window_service.grace_for_entry(db, existing) if existing is not None else grace
        )
        if override or row_grace != grace:
            r = work_window_service.clamp(
                db, user, entry_date, file_start, file_end, row_grace, credit_override=override,
            )
        segs = work_window_service.gap_segments(
            db, user, entry_date, file_start, file_end, row_grace, credit_override=override,
        )
        rows.append(SimpleNamespace(
            date=entry_date, note=note, r=r, segs=segs, existing=existing, override=override,
        ))
    return rows



def _apply_day_breaks(db: Session, user, user_id, tenant_id, day: date,
                      written: dict, logs: list) -> None:
    """``/confirm``: Tages-Pause der an ``day`` geschriebenen Einträge setzen und
    deren Protokollzeilen anlegen (Gesamtreview 1.20 B4).

    ``written`` = Eintrags-ID → (Eintrag, Lückensegmente) in Schreibreihenfolge,
    ``logs`` = (Protokollzeile, Eintrag). Mitgerechnet wird der Bestand des Tages,
    den der Import nicht angefasst hat — auch ein Konflikt, der ohne
    „überschreiben" stehen bleibt. Dieselbe Regel wie die Vorschau
    (``_day_break_minutes``). Die Protokollzeilen entstehen erst hier, weil
    ``new_break_minutes`` in den Manipulationsschutz ``row_hash`` (#121) eingeht."""
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
    breaks = _day_break_minutes([(e.start_time, e.end_time, segs) for e, segs in items], kept)
    for (e, _), minutes in zip(items, breaks):
        e.break_minutes = minutes
    for log, e in logs:
        log.new_break_minutes = e.break_minutes
        db.add(log)


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
        # Eintrags-ID → (Eintrag, Lückensegmente) in Schreibreihenfolge; die
        # Protokollzeilen entstehen erst mit der Tages-Pause (``new_break_minutes``).
        written: dict = {}
        logs: list = []
        for entry in day_entries:
            # Invariant end_time > start_time. net_hours floors a negative duration
            # to 0, so an end<=start row (over-midnight shift, or corrupt/forged
            # source — /confirm trusts client-supplied entries) would otherwise be
            # stored as a phantom 0h entry: wrong pay + it bypasses the §3 daily cap.
            # The interactive write paths reject this; the importer must too. Skip it
            # with a visible warning (over-midnight shifts are entered as two entries).
            if entry.end_time is None or entry.end_time <= entry.start_time:
                skipped += 1
                all_warnings.append(
                    f"{entry.date.strftime('%d.%m.%Y')}: übersprungen — Endzeit "
                    f"({entry.end_time.strftime('%H:%M') if entry.end_time else '—'}) "
                    f"liegt nicht nach Startzeit ({entry.start_time.strftime('%H:%M')}). "
                    f"Über-Mitternacht-Schichten als zwei Einträge erfassen."
                )
                continue

            # Release-Review 1.19.1 + Spec 7.4: NICHT den Client-Werten vertrauen.
            # /confirm nimmt die Einträge aus dem Request-Body entgegen; wo gekappt
            # wird, rechnet der Server Zeiten, raw_* und uncredited neu, und zwar
            # aus dem Rohwert (für eine unveränderte Vorschau identisch). Die
            # Auto-Pause rechnet er immer selbst (je Tag, ``_apply_day_breaks``).
            file_start = entry.raw_start_time or entry.start_time
            file_end = entry.raw_end_time or entry.end_time
            first = work_window_service.clamp(
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
                r = work_window_service.clamp(
                    db, target_user, entry.date, file_start, file_end, row_grace,
                    credit_override=False,
                )
                segs = work_window_service.gap_segments(
                    db, target_user, entry.date, file_start, file_end, row_grace,
                    credit_override=False,
                )
                eff_start, eff_end, raw_start, raw_end = r.eff_start, r.eff_end, r.raw_start, r.raw_end
                uncredited, applied_grace = r.uncredited_minutes, r.grace_minutes
            else:
                eff_start, eff_end = entry.start_time, entry.end_time
                raw_start, raw_end = entry.raw_start_time, entry.raw_end_time
                uncredited, applied_grace = 0, None
                # Spec 7.4: die Pause kommt nie vom Client — auch ohne Kappung
                # rechnet der Server sie (je Tag, unten).
                segs = []

            for w in entry.arbzg_warnings:
                all_warnings.append(f"{entry.date.strftime('%d.%m.%Y')}: {w}")

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
                overwritten += 1
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
                imported += 1

            # Eine doppelte Zeile der Datei überschreibt den eben angelegten Eintrag
            # — er zählt für den Tag nur einmal, an der späteren Stelle.
            written.pop(target.id, None)
            written[target.id] = (target, segs)
            logs.append((log, target))

        if written:
            _apply_day_breaks(db, target_user, user_id, tenant_id, day, written, logs)

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
