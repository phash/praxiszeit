"""
Service für den Import historischer Zeiterfassungsdaten aus TimeRec-XLS-Dateien.
Dateiformat: Sheet "Zeiterfassung", Spalten: Datum, Tag, Total, Ein, Aus, Tagesnotiz
"""
import uuid
import xlrd
from datetime import datetime, timedelta, date, time
from typing import Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models import TimeEntry, TimeEntryAuditLog, User
from app.services.arbzg_utils import is_night_work
from app.services import work_window_service

EXCEL_EPOCH = datetime(1899, 12, 30)
MAX_DAILY_NET_HOURS = 10.0   # §3 ArbZG
MIN_REST_HOURS = 11.0        # §5 ArbZG
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class ImportedEntry(BaseModel):
    date: date
    start_time: time
    end_time: time
    break_minutes: int
    note: Optional[str]
    has_conflict: bool
    arbzg_warnings: list[str]
    raw_start_time: Optional[time] = None
    raw_end_time: Optional[time] = None


class ImportResult(BaseModel):
    imported: int
    skipped: int
    overwritten: int
    warnings: list[str]


def _excel_serial_to_datetime(serial: float) -> datetime:
    """Konvertiert Excel-Serial-Datetime zu Python-datetime. Basis: 1899-12-30."""
    return EXCEL_EPOCH + timedelta(days=serial)


def _calc_break_minutes(start: time, end: time) -> int:
    """ArbZG §4: Pausen automatisch nach Brutto-Arbeitszeit berechnen."""
    # Note: assumes end > start (no overnight shifts). TimeRec format does not produce overnight entries.
    gross_seconds = (end.hour * 3600 + end.minute * 60) - (start.hour * 3600 + start.minute * 60)
    gross_hours = gross_seconds / 3600.0
    if gross_hours > 9:
        return 45
    elif gross_hours > 6:
        return 30
    return 0


NIGHT_WORKER_MAX_NET_HOURS = 8.0  # §6 Abs. 2 ArbZG: Nachtarbeitnehmer


def _check_arbzg(
    entry_date: date,
    start: time,
    end: time,
    break_min: int,
    prev_end_dt: Optional[datetime],
    exempt: bool = False,
    is_night_worker: bool = False,
    same_day_blocks: Optional[list[dict]] = None,
) -> list[str]:
    """ArbZG-Warnungen ermitteln (§3 Tageslimit, §4 Pause, §5 Ruhezeit, §6 Nachtarbeit).

    exempt=True (§18 ArbZG): alle Prüfungen werden übersprungen.
    is_night_worker=True (§6 Abs. 2 ArbZG): 8h-Limit statt 10h.
    same_day_blocks: Liste von {"start": time, "end": time, "break_minutes": int} für
        andere Einträge am selben Tag (aus Import-Batch + vorhandener DB). Wenn übergeben,
        werden §3 und §4 auf Basis der Tages-Aggregation statt des Einzeleintrags bewertet.
    """
    if exempt:
        return []

    warnings = []
    gross_seconds = (end.hour * 3600 + end.minute * 60) - (start.hour * 3600 + start.minute * 60)
    net_hours = (gross_seconds / 3600.0) - (break_min / 60.0)

    if same_day_blocks:
        # §3 / §4 Aggregation: alle Blöcke des Tages zusammenfassen (inkl. diesem Eintrag)
        all_blocks = list(same_day_blocks) + [{"start": start, "end": end, "break_minutes": break_min}]
        all_blocks.sort(key=lambda b: b["start"])

        total_gross_min = sum(
            (b["end"].hour * 60 + b["end"].minute) - (b["start"].hour * 60 + b["start"].minute)
            for b in all_blocks
        )
        total_declared_break_min = sum(
            b["break_minutes"] for b in all_blocks if b["break_minutes"] >= 15
        )
        # Lücken zwischen aufeinanderfolgenden Blöcken (≥15 min zählen als Pause)
        total_gap_min = 0
        for i in range(1, len(all_blocks)):
            gap = (
                (all_blocks[i]["start"].hour * 60 + all_blocks[i]["start"].minute)
                - (all_blocks[i - 1]["end"].hour * 60 + all_blocks[i - 1]["end"].minute)
            )
            if gap >= 15:
                total_gap_min += gap
        total_net_min = total_gross_min - total_declared_break_min
        total_net_hours = total_net_min / 60.0
        total_effective_break = total_declared_break_min + total_gap_min

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
        curr_start_dt = datetime.combine(entry_date, start)
        rest_hours = (curr_start_dt - prev_end_dt).total_seconds() / 3600.0
        if rest_hours < MIN_REST_HOURS:
            warnings.append(
                f"§5 ArbZG: Ruhezeit {rest_hours:.1f}h unterschreitet das 11h-Minimum "
                f"(vorheriger Eintrag endete {prev_end_dt.strftime('%d.%m.%Y %H:%M')})"
            )

    return warnings


def parse_xls(file_bytes: bytes, user_id: uuid.UUID, db: Session) -> list[ImportedEntry]:
    """
    Parst eine TimeRec-XLS-Datei und gibt ImportedEntry-Liste zurück.
    Ermittelt Konflikte (user_id+date+start_time) und ArbZG-Warnungen.

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
    user = db.query(User).filter(User.id == user_id).first()
    exempt = getattr(user, "exempt_from_arbzg", False) or False
    is_night_worker = getattr(user, "is_night_worker", False) or False

    # #201: Soll-Fenster-Puffer einmalig laden (Default 15 min)
    grace = work_window_service.get_grace_minutes(db, user.tenant_id) if user else work_window_service.DEFAULT_GRACE_MINUTES

    ws = wb.sheet_by_name("Zeiterfassung")
    entries: list[ImportedEntry] = []
    prev_end_dt: Optional[datetime] = None
    first_import_date: Optional[date] = None

    # §3/§4 Tagesaggregation: Blöcke pro Datum sammeln (Import-Batch + DB-Einträge bereits gecacht)
    # batch_blocks_by_date: date -> list of {"start": time, "end": time, "break_minutes": int}
    batch_blocks_by_date: dict[date, list[dict]] = {}
    # db_blocks_by_date: gecachte DB-Einträge pro Datum (einmalig pro Datum abgefragt)
    db_blocks_by_date: dict[date, list[dict]] = {}

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
        start_t = ein_dt.time().replace(second=0, microsecond=0)
        end_t = aus_dt.time().replace(second=0, microsecond=0)

        # #201: Soll-Fenster kappen; raw_* nur gesetzt wenn gekappt
        if user is not None:
            start_t, end_t, raw_start_t, raw_end_t = work_window_service.clamp(
                user, entry_date, start_t, end_t, grace
            )
        else:
            raw_start_t = raw_end_t = None

        break_min = _calc_break_minutes(start_t, end_t)

        # §5-Check: Für den ersten Eintrag im Import letzten DB-Eintrag vor Import-Zeitraum holen
        check_prev = prev_end_dt
        if first_import_date is None:
            first_import_date = entry_date
            last_db_entry = (
                db.query(TimeEntry)
                .filter(TimeEntry.user_id == user_id, TimeEntry.date < entry_date)
                .order_by(TimeEntry.date.desc(), TimeEntry.start_time.desc())
                .first()
            )
            if last_db_entry and last_db_entry.end_time:
                check_prev = datetime.combine(last_db_entry.date, last_db_entry.end_time)

        # §3/§4 Tagesaggregation: bestehende DB-Einträge für diesen Tag einmalig laden
        if entry_date not in db_blocks_by_date:
            db_entries_today = (
                db.query(TimeEntry)
                .filter(TimeEntry.user_id == user_id, TimeEntry.date == entry_date)
                .all()
            )
            db_blocks_by_date[entry_date] = [
                {"start": e.start_time, "end": e.end_time, "break_minutes": e.break_minutes}
                for e in db_entries_today
                if e.end_time is not None
            ]

        # Alle anderen Blöcke am selben Tag = DB-Blöcke + bisher im Batch gesammelte Blöcke
        other_blocks = db_blocks_by_date[entry_date] + batch_blocks_by_date.get(entry_date, [])

        arbzg_warnings = _check_arbzg(
            entry_date, start_t, end_t, break_min, check_prev,
            exempt=exempt, is_night_worker=is_night_worker,
            same_day_blocks=other_blocks if other_blocks else None,
        )

        # Diesen Block für nachfolgende Zeilen am selben Tag merken
        if entry_date not in batch_blocks_by_date:
            batch_blocks_by_date[entry_date] = []
        batch_blocks_by_date[entry_date].append({"start": start_t, "end": end_t, "break_minutes": break_min})

        # Konflikt-Check nach UniqueConstraint (user_id + date + start_time)
        existing = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user_id,
                TimeEntry.date == entry_date,
                TimeEntry.start_time == start_t,
            )
            .first()
        )

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
        ))

        prev_end_dt = datetime.combine(entry_date, end_t)

    if not entries:
        raise ValueError("Keine Datenzeilen im Sheet 'Zeiterfassung' gefunden")

    return entries


def execute_import(
    user_id: uuid.UUID,
    entries: list[ImportedEntry],
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
    entries: list[ImportedEntry],
    overwrite: bool,
    db: Session,
    changed_by_id: uuid.UUID,
    filename: str,
    tenant_id: uuid.UUID | None = None,
) -> ImportResult:
    """Actual import body. Callers should use execute_import() which wraps it."""
    imported = 0
    skipped = 0
    overwritten = 0
    all_warnings: list[str] = []

    for entry in entries:
        for w in entry.arbzg_warnings:
            all_warnings.append(f"{entry.date.strftime('%d.%m.%Y')}: {w}")

        # Re-query conflict: has_conflict on ImportedEntry reflects preview state.
        # A new entry may have been created between preview and confirm, so we
        # re-check here rather than trusting the frontend's has_conflict flag.
        existing = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user_id,
                TimeEntry.date == entry.date,
                TimeEntry.start_time == entry.start_time,
            )
            .first()
        )

        if existing:
            if not overwrite:
                skipped += 1
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
                new_start_time=entry.start_time,
                new_end_time=entry.end_time,
                new_break_minutes=entry.break_minutes,
                new_note=entry.note,
                tenant_id=tenant_id,
            )
            existing.end_time = entry.end_time
            existing.break_minutes = entry.break_minutes
            existing.note = entry.note
            # Audit R3/§16: Roh-Stempel des Import-Eintrags übernehmen, sonst
            # geht der Nachweis der tatsächlichen Anwesenheit beim Overwrite
            # verloren (gekappter Wert bliebe, Rohwert verschwände).
            existing.raw_start_time = entry.raw_start_time
            existing.raw_end_time = entry.raw_end_time
            db.add(log)
            overwritten += 1
        else:
            new_entry = TimeEntry(
                user_id=user_id,
                tenant_id=tenant_id,
                date=entry.date,
                start_time=entry.start_time,
                end_time=entry.end_time,
                break_minutes=entry.break_minutes,
                note=entry.note,
                raw_start_time=entry.raw_start_time,
                raw_end_time=entry.raw_end_time,
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
                new_start_time=entry.start_time,
                new_end_time=entry.end_time,
                new_break_minutes=entry.break_minutes,
                new_note=entry.note,
                tenant_id=tenant_id,
            )
            db.add(log)
            imported += 1

    # Zusammenfassungs-Eintrag im Audit-Log (action="import", time_entry_id=None)
    target_user = db.query(User).filter(User.id == user_id).first()
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
