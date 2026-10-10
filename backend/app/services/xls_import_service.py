"""
Service für den Import historischer Zeiterfassungsdaten aus TimeRec-XLS-Dateien.
Dateiformat: Sheet "Zeiterfassung", Spalten: Datum, Tag, Total, Ein, Aus, Tagesnotiz
"""
import uuid
import xlrd
from datetime import datetime, timedelta, date, time
from types import SimpleNamespace
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from pydantic import BaseModel, computed_field

from app.models import TimeEntry, TimeEntryAuditLog, User
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
    start_time: time
    end_time: time
    break_minutes: int
    note: Optional[str]
    has_conflict: bool
    arbzg_warnings: list[str]
    raw_start_time: Optional[time] = None
    raw_end_time: Optional[time] = None


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


def _min(t: time) -> int:
    return t.hour * 60 + t.minute


def _calc_break_minutes(eff_start: time, eff_end: time, segments: Sequence[int]) -> int:
    """ArbZG §4: Auto-Pause aus der ANGERECHNETEN Bruttozeit (Spec 7.4).

    ``segments`` = ``work_window_service.gap_segments`` der Zeile. Lückensegmente
    >= 15 Min decken den Bedarf als Pausenabschnitt; nachgetragen wird nur, was
    fehlt — sonst zöge der Import eine Pause in der Lücke ein zweites Mal ab
    (Doppelabzug, E45). Ein Rest unter 15 Min wird auf 15 aufgerundet (§4 Satz 2).
    Ohne Blöcke (``segments == []``) byte-identisch zur bisherigen Regel.
    Note: assumes end > start (no overnight shifts) — TimeRec liefert keine."""
    credited_gross = (_min(eff_end) - _min(eff_start)) - sum(segments)
    required = 45 if credited_gross > 9 * 60 else 30 if credited_gross > 6 * 60 else 0
    covered = sum(s for s in segments if s >= 15)
    rest = max(0, required - covered)
    return 15 if 0 < rest < 15 else rest


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
    """
    if exempt:
        return []

    warnings = []
    own = break_block_for_new(start, end, break_min, uncredited_segments)
    net_hours = (own.end - own.start - own.deduct_minutes) / 60.0 - break_min / 60.0

    if same_day_blocks:
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
    entries: list[ImportedEntry] = []
    prev_end_dt: Optional[datetime] = None
    first_import_date: Optional[date] = None

    # §3/§4 Tagesaggregation: BreakBlocks pro Datum (Import-Batch + DB-Einträge)
    batch_blocks_by_date: dict[date, list[BreakBlock]] = {}
    db_blocks_by_date: dict[date, list[BreakBlock]] = {}

    # Spec 8.3 (PR2): Anwesenheit laut Stempel je Kalenderwoche (Tag und Woche,
    # P22) — Bestand + bisherige Zeilen der Datei; von einer Importzeile
    # überschriebene Bestandseinträge zählen nicht mit (Review Focus 4).
    db_presence_by_week: dict[date, list] = {}
    batch_presence_by_week: dict[date, list] = {}
    replaced_ids: set = set()

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
        start_t, end_t = r.eff_start, r.eff_end
        raw_start_t, raw_end_t = r.raw_start, r.raw_end

        break_min = _calc_break_minutes(start_t, end_t, segs)

        # §5-Check: Für den ersten Eintrag im Import letzten DB-Eintrag vor Import-Zeitraum holen.
        # Spec 7.3: gegen den ROHSTEMPEL (raw_end or end) wie rest_time_service.
        check_prev = prev_end_dt
        if first_import_date is None:
            first_import_date = entry_date
            last_db_entry = (
                db.query(TimeEntry)
                .filter(
                    TimeEntry.user_id == user_id,
                    TimeEntry.tenant_id == user_tenant,  # F-026
                    TimeEntry.date < entry_date,
                )
                .order_by(TimeEntry.date.desc(), TimeEntry.start_time.desc())
                .first()
            )
            if last_db_entry and last_db_entry.end_time:
                check_prev = datetime.combine(
                    last_db_entry.date, last_db_entry.raw_end_time or last_db_entry.end_time,
                )

        # §3/§4 Tagesaggregation: bestehende DB-Einträge für diesen Tag einmalig laden
        if entry_date not in db_blocks_by_date:
            db_blocks_by_date[entry_date] = [
                break_block_for_entry(db, user, e)
                for e in db.query(TimeEntry).filter(
                    TimeEntry.user_id == user_id,
                    TimeEntry.tenant_id == user_tenant,  # F-026
                    TimeEntry.date == entry_date,
                ).all()
                if e.end_time is not None
            ]

        # Alle anderen Blöcke am selben Tag = DB-Blöcke + bisher im Batch gesammelte Blöcke
        other_blocks = db_blocks_by_date[entry_date] + batch_blocks_by_date.get(entry_date, [])

        arbzg_warnings = _check_arbzg(
            entry_date, start_t, end_t, break_min, check_prev,
            exempt=exempt, is_night_worker=is_night_worker,
            same_day_blocks=other_blocks if other_blocks else None,
            uncredited_segments=segs,
            rest_start=raw_start_t or start_t,
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

        # Spec 8.3/8.4: weiche Anwesenheits-Hinweise (Tag, Woche, Pause in der
        # Lücke) als Klartext ohne Code — dieselben Regeln wie in den
        # Schreibpfaden (presence_service.presence_hints). §18 → keine.
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
            if existing is not None:
                replaced_ids.add(existing.id)
            week_rows = (
                [e for e in db_presence_by_week[monday] if e.id not in replaced_ids]
                + batch_presence_by_week.get(monday, [])
                + [row_view]
            )
            hints = presence_service.presence_hints(
                row_view, [e for e in week_rows if e.date == entry_date], week_rows,
                break_check_passed=break_passed,
            )
            arbzg_warnings = arbzg_warnings + [presence_service.plain_text(h) for h in hints]
            batch_presence_by_week.setdefault(monday, []).append(row_view)

        # Diesen Block für nachfolgende Zeilen am selben Tag merken
        batch_blocks_by_date.setdefault(entry_date, []).append(
            break_block_for_new(start_t, end_t, break_min, segs)
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
            uncredited_minutes=r.uncredited_minutes,
            net_hours=net,
        ))

        prev_end_dt = datetime.combine(entry_date, raw_end_t or end_t)

    if not entries:
        raise ValueError("Keine Datenzeilen im Sheet 'Zeiterfassung' gefunden")

    return entries


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

    for entry in entries:
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
        # wird, rechnet der Server Zeiten, raw_*, uncredited UND Auto-Pause neu,
        # und zwar aus dem Rohwert (für eine unveränderte Vorschau identisch).
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
            break_minutes = _calc_break_minutes(eff_start, eff_end, segs)
        else:
            eff_start, eff_end = entry.start_time, entry.end_time
            raw_start, raw_end = entry.raw_start_time, entry.raw_end_time
            uncredited, applied_grace = 0, None
            break_minutes = entry.break_minutes

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
                new_break_minutes=break_minutes,
                new_note=entry.note,
                tenant_id=tenant_id,
            )
            existing.start_time = eff_start
            existing.end_time = eff_end
            existing.break_minutes = break_minutes
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
            db.add(log)
            overwritten += 1
        else:
            new_entry = TimeEntry(
                user_id=user_id,
                tenant_id=tenant_id,
                date=entry.date,
                start_time=eff_start,
                end_time=eff_end,
                break_minutes=break_minutes,
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
                new_break_minutes=break_minutes,
                new_note=entry.note,
                tenant_id=tenant_id,
            )
            db.add(log)
            imported += 1

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
