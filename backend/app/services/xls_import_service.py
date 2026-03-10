"""
Service für den Import historischer Zeiterfassungsdaten aus TimeRec-XLS-Dateien.
Dateiformat: Sheet "Zeiterfassung", Spalten: Datum, Tag, Total, Ein, Aus, Tagesnotiz
"""
import xlrd
from datetime import datetime, timedelta, date, time
from typing import Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models import TimeEntry, User
from app.services.arbzg_utils import is_night_work

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
    gross_seconds = (end.hour * 3600 + end.minute * 60) - (start.hour * 3600 + start.minute * 60)
    gross_hours = gross_seconds / 3600.0
    if gross_hours > 9:
        return 45
    elif gross_hours > 6:
        return 30
    return 0


def _check_arbzg(
    entry_date: date,
    start: time,
    end: time,
    break_min: int,
    prev_end_dt: Optional[datetime],
) -> list[str]:
    """ArbZG-Warnungen ermitteln (§3 Tageslimit, §5 Ruhezeit, §6 Nachtarbeit)."""
    warnings = []
    gross_seconds = (end.hour * 3600 + end.minute * 60) - (start.hour * 3600 + start.minute * 60)
    net_hours = (gross_seconds / 3600.0) - (break_min / 60.0)

    if net_hours > MAX_DAILY_NET_HOURS:
        warnings.append(f"§3 ArbZG: Tägliche Netto-Arbeitszeit {net_hours:.1f}h überschreitet 10h-Limit")

    if is_night_work(start, end):
        warnings.append("§6 ArbZG: Nachtarbeit erkannt (>2h zwischen 23:00–06:00)")

    if prev_end_dt is not None:
        curr_start_dt = datetime.combine(entry_date, start)
        rest_hours = (curr_start_dt - prev_end_dt).total_seconds() / 3600.0
        if rest_hours < MIN_REST_HOURS:
            warnings.append(
                f"§5 ArbZG: Ruhezeit {rest_hours:.1f}h unterschreitet 11h-Minimum "
                f"(Vorletzter Eintrag endete {prev_end_dt.strftime('%d.%m %H:%M')})"
            )

    return warnings


def parse_xls(file_bytes: bytes, user_id, db: Session) -> list[ImportedEntry]:
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

    ws = wb.sheet_by_name("Zeiterfassung")
    entries: list[ImportedEntry] = []
    prev_end_dt: Optional[datetime] = None
    first_import_date: Optional[date] = None

    for row_idx in range(ws.nrows):
        # Datenzeile erkennbar durch numerischen ctype (3) in Ein-Spalte (D)
        if ws.cell(row_idx, 3).ctype != 3:
            continue

        ein_serial = ws.cell_value(row_idx, 3)
        aus_serial = ws.cell_value(row_idx, 4)
        notiz_raw = ws.cell_value(row_idx, 5)

        ein_dt = _excel_serial_to_datetime(ein_serial)
        aus_dt = _excel_serial_to_datetime(aus_serial)
        note = str(notiz_raw).strip() if notiz_raw else None

        entry_date = ein_dt.date()
        # Sekunden auf 0 setzen (XLS hat keine Sekunden)
        start_t = ein_dt.time().replace(second=0, microsecond=0)
        end_t = aus_dt.time().replace(second=0, microsecond=0)
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

        arbzg_warnings = _check_arbzg(entry_date, start_t, end_t, break_min, check_prev)

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
        ))

        prev_end_dt = datetime.combine(entry_date, end_t)

    if not entries:
        raise ValueError("Keine Datenzeilen im Sheet 'Zeiterfassung' gefunden")

    return entries


def execute_import(
    user_id,
    entries: list[ImportedEntry],
    overwrite: bool,
    db: Session,
    changed_by_id,
    filename: str,
) -> ImportResult:
    """
    Führt den Import durch. Bei overwrite=True werden Konflikte überschrieben,
    sonst übersprungen. Schreibt Audit-Log-Einträge.
    """
    from app.models import TimeEntryAuditLog

    imported = 0
    skipped = 0
    overwritten = 0
    all_warnings: list[str] = []

    for entry in entries:
        for w in entry.arbzg_warnings:
            all_warnings.append(f"{entry.date.strftime('%d.%m.%Y')}: {w}")

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
            )
            existing.end_time = entry.end_time
            existing.break_minutes = entry.break_minutes
            existing.note = entry.note
            db.add(log)
            overwritten += 1
        else:
            new_entry = TimeEntry(
                user_id=user_id,
                date=entry.date,
                start_time=entry.start_time,
                end_time=entry.end_time,
                break_minutes=entry.break_minutes,
                note=entry.note,
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
    )
    db.add(summary_log)
    db.commit()

    return ImportResult(
        imported=imported,
        skipped=skipped,
        overwritten=overwritten,
        warnings=all_warnings,
    )
