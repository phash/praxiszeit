"""Admin sub-router: Admin Time Entry CRUD + Audit Log."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.services.date_filters import date_in_year, date_in_month
from sqlalchemy import extract, or_, and_
from typing import List, Optional
from app.database import get_db
from app.models import User, TimeEntry, TimeEntryAuditLog
from app.middleware.auth import require_admin
from app.schemas.time_entry import TimeEntryCreate, TimeEntryResponse, TimeEntryUpdate
from app.schemas.time_entry_audit_log import AuditLogResponse
from app.routers.admin_helpers import _create_audit_log, _enrich_audit_response, _enrich_audit_responses
from app.services.break_validation_service import validate_daily_break
from app.routers.time_entries import (
    _calculate_daily_net_hours, _calculate_weekly_net_hours,
    MAX_DAILY_HOURS_HARD, MAX_DAILY_HOURS_WARN, MAX_NIGHT_WORKER_DAILY_WARN, MAX_WEEKLY_HOURS_WARN,
    BREAK_WAIVER_SOURCE,
)
from app.services.arbzg_utils import is_night_work
from app.services import work_window_service
from app.routers.absences import _MASKED_ABSENCE_TYPES
from app.services.export_service import ABSENCE_TYPE_LABELS_DE

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# #284: The audit table stores BOTH real changes to time entries/absences
# (create/update/delete) AND access/system events (e.g. DSGVO read-access markers
# 'absence_list_read'/'health_data_read' written on every admin open of an
# employee, #208). The operational per-employee "Änderungsprotokoll" must show
# only the former; otherwise every open spawns a fresh access-log row that the
# UI rendered as a phantom "Gelöscht". The dedicated compliance audit page keeps
# full visibility (changes_only=False).
_CHANGE_ACTIONS = ("create", "update", "delete")

# #431 / Art. 5(2) + Art. 9 DSGVO: Marker der Zugriffsvermerke dieser Fläche.
# `action` ist varchar(40) (Migration 044) — beide Werte bleiben deutlich darunter.
# ``audit_log_read`` wird seit Fix-Welle 4 (#2) nicht mehr NEU geschrieben
# (siehe Kommentar in list_audit_log) — bleibt hier für ältere Bestandszeilen
# und den varchar-Limit-Test erhalten.
_AUDIT_READ_ACTIONS = ("health_data_read", "audit_log_read")

# Welche Audit-Notiz trägt einen gesundheitsbezogenen Abwesenheitstyp?
# Zwei Notiz-Formate können einen Typ führen:
#   * maschinell  ``absence:<typ>:<stunden>h``   (Buchung/Storno/CR-Genehmigung)
#   * Klartext    ``Krank 8,0 h — <Auslöser>``   (#431 Rückrechnung, _wh_change_audit)
# Beide Muster werden aus DERSELBEN Quelle abgeleitet wie die Maskierung der
# Kollegen-Feeds (``absences._MASKED_ABSENCE_TYPES``) — kommt dort ein Typ hinzu,
# greift er hier automatisch mit, statt still zu divergieren.
_SENSITIVE_NOTE_TOKENS = tuple(
    f"absence:{t.value}:" for t in _MASKED_ABSENCE_TYPES
) + tuple(
    ABSENCE_TYPE_LABELS_DE[t.value] + " "
    for t in _MASKED_ABSENCE_TYPES
    if t.value in ABSENCE_TYPE_LABELS_DE
)


def _audit_note_is_health_sensitive(log: TimeEntryAuditLog) -> bool:
    """True, wenn ``old_note``/``new_note`` einen maskierten Abwesenheitstyp nennt."""
    for note in (log.old_note, log.new_note):
        if note and any(token in note for token in _SENSITIVE_NOTE_TOKENS):
            return True
    return False


# ── Admin Time Entry Management ─────────────────────────────────────────

@router.post("/users/{user_id}/time-entries", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def admin_create_time_entry(
    user_id: str,
    entry_data: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin creates a time entry for an employee."""
    # F-026: explicit tenant scoping on user lookup (don't rely on RLS alone)
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user.tenant_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # #201: Clamp start/end to the employee's soll window (grace from tenant setting).
    # The affected employee is `user`, NOT the admin (current_user).
    _grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(
        user, entry_data.date, entry_data.start_time, entry_data.end_time, _grace,
    )

    # #375-Review: mirror the employee path's duplicate-start guard, BEFORE the
    # ArbZG aggregate checks. The admin per-day journal add is now available for
    # TODAY, where a manual entry can collide with an existing/open clock-in
    # sharing the (clamped) start minute. Without this the (tenant, user, date,
    # start_time) UNIQUE constraint raises an IntegrityError on commit → HTTP 500;
    # return a clean 409 instead (SQLite ignores the constraint, so this app-level
    # check is what actually protects both engines).
    duplicate = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
        TimeEntry.date == entry_data.date,
        TimeEntry.start_time == eff_start,
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es existiert bereits ein Eintrag mit dieser Startzeit an diesem Datum",
        )

    admin_create_warnings: list[str] = []
    # #462: Die Kappung darf nicht stumm passieren — genau der Fall, den der
    # Melder als "Rundung auf Viertelstunden" wahrgenommen hat.
    _clamp_warn = work_window_service.clamp_warning(
        raw_start, raw_end, eff_start, eff_end, _grace,
    )
    if _clamp_warn:
        admin_create_warnings.append(_clamp_warn)
    waiver_reason = (entry_data.break_waiver_reason or "").strip()
    break_waiver_active = False
    if not user.exempt_from_arbzg:
        # Break validation (§4 ArbZG) — use clamped times
        break_error = validate_daily_break(
            db=db, user_id=user.id, entry_date=entry_data.date,
            start_time=eff_start, end_time=eff_end,
            break_minutes=entry_data.break_minutes,
        )
        if break_error:
            # M-ARB3: parity with the employee path (#144) — a documented break
            # waiver lets the admin record the §4 deviation instead of being
            # hard-blocked. §3 (10h hard cap, below) is checked afterwards and
            # is NOT waivable.
            if not waiver_reason:
                raise HTTPException(status_code=400, detail=break_error)
            break_waiver_active = True
            admin_create_warnings.append(f"BREAK_WAIVER: {break_error}")

        # SS3 ArbZG: daily hours hard limit — use clamped times
        daily_hours = _calculate_daily_net_hours(
            db=db, user_id=user.id, entry_date=entry_data.date,
            start_time=eff_start, end_time=eff_end,
            break_minutes=entry_data.break_minutes,
            tenant_id=current_user.tenant_id,
        )
        if daily_hours > MAX_DAILY_HOURS_HARD:
            raise HTTPException(
                status_code=422,
                detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
            )

        # §3 ArbZG: Warnung bei Überschreitung der Regelgrenze (8h)
        if daily_hours > MAX_DAILY_HOURS_WARN:
            admin_create_warnings.append(f"DAILY_HOURS_WARNING: Tagesarbeitszeit beträgt {daily_hours:.1f}h (>{MAX_DAILY_HOURS_WARN}h)")

        # §3 ArbZG: Warnung bei Überschreitung der 48h-Wochengrenze
        weekly_hours = _calculate_weekly_net_hours(
            db=db, user_id=user.id, entry_date=entry_data.date,
            start_time=eff_start, end_time=eff_end,
            break_minutes=entry_data.break_minutes,
            tenant_id=current_user.tenant_id,
        )
        if weekly_hours > MAX_WEEKLY_HOURS_WARN:
            admin_create_warnings.append(f"WEEKLY_HOURS_WARNING: Wochenarbeitszeit beträgt {weekly_hours:.1f}h (>{MAX_WEEKLY_HOURS_WARN}h, §3 ArbZG)")

        # SS6 Abs. 2 ArbZG: Warnung für Nachtarbeitnehmer
        if (
            user.is_night_worker
            and is_night_work(eff_start, eff_end)
            and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            admin_create_warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    entry = TimeEntry(
        user_id=user.id,
        tenant_id=current_user.tenant_id,
        date=entry_data.date,
        start_time=eff_start,
        end_time=eff_end,
        break_minutes=entry_data.break_minutes,
        note=entry_data.note,
        break_waiver_reason=waiver_reason if break_waiver_active else None,
        raw_start_time=raw_start,
        raw_end_time=raw_end,
    )
    db.add(entry)
    db.flush()

    _create_audit_log(
        db, entry.id, user.id, current_user.id,
        action="create", new_entry=entry,
        source=BREAK_WAIVER_SOURCE if break_waiver_active else "manual",
        tenant_id=current_user.tenant_id,
    )

    db.commit()
    db.refresh(entry)
    response = TimeEntryResponse.model_validate(entry)
    response.warnings = admin_create_warnings
    return response


@router.put("/time-entries/{entry_id}", response_model=TimeEntryResponse)
def admin_update_time_entry(
    entry_id: str,
    entry_data: TimeEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin updates a time entry with audit logging."""
    # F-028: lock the row so two concurrent admin edits can't race between
    # validation and apply — otherwise state-B is written while state-A was
    # validated.
    entry = (
        db.query(TimeEntry)
        .filter(
            TimeEntry.id == entry_id,
            TimeEntry.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Get user for SS18 exempt check and night worker warning.
    # F-026: expliziter Tenant-Filter zusätzlich zu RLS (belt-and-suspenders).
    affected_user = db.query(User).filter(
        User.id == entry.user_id,
        User.tenant_id == current_user.tenant_id,
    ).first()

    # Use provided values or fall back to existing.
    # Release-Review 1.18.2: der Rückfallwert ist der ROHSTEMPEL, nicht die
    # gespeicherte (bereits gekappte) Zeit. ``entry.start_time`` als Kappungs-
    # Eingabe hieß: eine reine Datumsänderung kappte das Ergebnis der letzten
    # Kappung ein zweites Mal und schrieb es anschließend als neuen „Rohwert"
    # fest (``_times_affected`` gilt auch bei einem Datums-only-PUT). Der echte
    # Stempel war damit unwiederbringlich weg — das Audit-Log führt nur
    # date/start/end/break, keine raw_*-Felder. Er ist aber der §16-Nachweis der
    # tatsächlichen Anwesenheit und laut CLAUDE.md die Grundlage der
    # §5-Ruhezeitprüfung; danach rechnete § 5 gegen die geschönte Zeit und ein
    # echter Verstoß blieb unentdeckt. ``clamp`` leitet aus dem Rohwert für den
    # neuen Wochentag wieder korrekt eff_* UND raw_* ab.
    update_date = entry_data.date if entry_data.date is not None else entry.date
    update_start_time = (
        entry_data.start_time if entry_data.start_time is not None
        else (entry.raw_start_time or entry.start_time)
    )
    update_end_time = (
        entry_data.end_time if entry_data.end_time is not None
        else (entry.raw_end_time or entry.end_time)
    )
    update_break_minutes = entry_data.break_minutes if entry_data.break_minutes is not None else entry.break_minutes

    # Release-Review 1.16.0: die Reihenfolge des GEMERGTEN Paars prüfen.
    # `TimeEntryUpdate.validate_end_after_start` sieht nur den Payload — ein PUT mit
    # ausschliesslich `end_time` kommt daran vorbei, und der Router schrieb bisher
    # end < start durch; `net_hours` fiel dann still über den max(0,…)-Floor auf 0
    # und der Tag verschwand aus Saldo und §16-Beleg.
    if (
        update_start_time is not None
        and update_end_time is not None
        and update_end_time <= update_start_time
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Endzeit muss nach Startzeit liegen",
        )

    # Release-Review 1.19.1: Schickt das Formular die ANGERECHNETE Zeit unveraendert
    # zurueck (es fuellt sich damit), ist das keine Eingabe — sondern derselbe
    # Eintrag. Ohne diese Ruecksetzung sah ``clamp`` darin eine neue,
    # fensterkonforme Zeit und setzte raw_* auf None: der §16-Rohstempel war nach
    # einer blossen Notiz- oder Pausenkorrektur weg (und mit ihm die Grundlage der
    # §5-Ruhezeitpruefung). Derselbe Schaden wie beim Datums-Edit aus 1.18.2, nur
    # ueber den zweiten Weg.
    update_start_time = work_window_service.unclamp_input(
        update_start_time, entry.start_time, entry.raw_start_time,
    )
    update_end_time = work_window_service.unclamp_input(
        update_end_time, entry.end_time, entry.raw_end_time,
    )

    # #201: Clamp start/end to the affected employee's soll window.
    # Use `affected_user` (the employee whose entry this is), NOT current_user (admin).
    _grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    if affected_user is not None:
        eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(
            affected_user, update_date, update_start_time, update_end_time, _grace,
        )
    else:
        eff_start, eff_end, raw_start, raw_end = update_start_time, update_end_time, None, None

    # #375-Review: mirror the create-path duplicate-start guard (exclude self) —
    # editing start_time/date onto an existing sibling entry would otherwise hit
    # the (tenant, user, date, start_time) UNIQUE constraint → IntegrityError →
    # HTTP 500 on Postgres. Return a clean 409 instead.
    dup = db.query(TimeEntry).filter(
        TimeEntry.user_id == entry.user_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
        TimeEntry.date == update_date,
        TimeEntry.start_time == eff_start,
        TimeEntry.id != entry.id,
    ).first()
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es existiert bereits ein Eintrag mit dieser Startzeit an diesem Datum",
        )

    admin_update_warnings: list[str] = []
    # #462: wie im Anlege-Pfad — eine stille Aenderung fremder Arbeitszeit ist
    # das eigentliche Problem, nicht die Kappung selbst. Nur melden, wenn die
    # gekappte Zeit auch tatsaechlich geschrieben wird: eine reine
    # Notiz-Aenderung fasst start/end nicht an (Fix #2 weiter unten) und darf
    # deshalb auch nicht ueber eine Kappung berichten.
    # Release-Review 1.19.1: Massstab ist nicht "war ein Zeitfeld im Payload",
    # sondern "hat sich die eingereichte Zeit gegenueber der gespeicherten
    # geaendert". Das Formular schickt die angerechnete Zeit immer mit; ohne
    # diesen Vergleich meldete jede Notiz- oder Pausenkorrektur erneut eine
    # Kappung, die laengst passiert ist — derselbe Laerm, den der Notiz-Gate
    # vermeiden sollte. ``entry.*`` traegt an dieser Stelle noch den gespeicherten
    # Stand (geschrieben wird weiter unten).
    _times_written = (
        entry_data.date is not None
        and entry_data.date != entry.date
    ) or update_start_time != (entry.raw_start_time or entry.start_time) \
      or update_end_time != (entry.raw_end_time or entry.end_time)
    if _times_written:
        _clamp_warn = work_window_service.clamp_warning(
            raw_start, raw_end, eff_start, eff_end, _grace,
        )
        if _clamp_warn:
            admin_update_warnings.append(_clamp_warn)
    waiver_reason = (entry_data.break_waiver_reason or "").strip()
    break_waiver_active = False
    if not affected_user or not affected_user.exempt_from_arbzg:
        # Break validation (§4 ArbZG) — use clamped times
        break_error = validate_daily_break(
            db=db, user_id=entry.user_id, entry_date=update_date,
            start_time=eff_start, end_time=eff_end,
            break_minutes=update_break_minutes, exclude_entry_id=entry.id,
        )
        if break_error:
            # M-ARB3: parity with the employee path (#144) — documented waiver
            # records the §4 deviation instead of a hard 400. §3 (below) stays
            # a hard cap.
            if not waiver_reason:
                raise HTTPException(status_code=400, detail=break_error)
            break_waiver_active = True
            admin_update_warnings.append(f"BREAK_WAIVER: {break_error}")

        # SS3 ArbZG: daily hours hard limit — use clamped times
        daily_hours = _calculate_daily_net_hours(
            db=db, user_id=entry.user_id, entry_date=update_date,
            start_time=eff_start, end_time=eff_end,
            break_minutes=update_break_minutes, exclude_entry_id=entry.id,
            tenant_id=current_user.tenant_id,
        )
        if daily_hours > MAX_DAILY_HOURS_HARD:
            raise HTTPException(
                status_code=422,
                detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
            )

        # §3 ArbZG: Warnung bei Überschreitung der Regelgrenze (8h)
        if daily_hours > MAX_DAILY_HOURS_WARN:
            admin_update_warnings.append(f"DAILY_HOURS_WARNING: Tagesarbeitszeit beträgt {daily_hours:.1f}h (>{MAX_DAILY_HOURS_WARN}h)")

        # §3 ArbZG: Warnung bei Überschreitung der 48h-Wochengrenze
        weekly_hours = _calculate_weekly_net_hours(
            db=db, user_id=entry.user_id, entry_date=update_date,
            start_time=eff_start, end_time=eff_end,
            break_minutes=update_break_minutes, exclude_entry_id=entry.id,
            tenant_id=current_user.tenant_id,
        )
        if weekly_hours > MAX_WEEKLY_HOURS_WARN:
            admin_update_warnings.append(f"WEEKLY_HOURS_WARNING: Wochenarbeitszeit beträgt {weekly_hours:.1f}h (>{MAX_WEEKLY_HOURS_WARN}h, §3 ArbZG)")

        # SS6 Abs. 2 ArbZG: Warnung für Nachtarbeitnehmer
        if (
            affected_user
            and affected_user.is_night_worker
            and is_night_work(eff_start, eff_end)
            and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            admin_update_warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    # Create audit log before changing
    _create_audit_log(
        db, entry.id, entry.user_id, current_user.id,
        action="update", old_entry=entry,
        new_entry={
            "date": update_date,
            "start_time": eff_start,
            "end_time": eff_end,
            "break_minutes": update_break_minutes,
            "note": entry_data.note if entry_data.note is not None else entry.note,
        },
        source=BREAK_WAIVER_SOURCE if break_waiver_active else "manual",
        tenant_id=current_user.tenant_id,
    )

    # Apply only provided updates (always write clamped effective times).
    # Release-Review 1.16.0: ein Datumswechsel ändert das Soll-Fenster des Tages und
    # damit das Kappungsergebnis, auch wenn keine Zeit mitgeschickt wurde. Vorher
    # wurden Validierung, Duplikatsprüfung und Audit-Log mit den NEU gekappten Zeiten
    # gefahren, in die DB aber die alten geschrieben — der Audit-Eintrag behauptete
    # eine Zeit, die nie gespeichert wurde, und das #201-Arbeitszeitfenster liess
    # sich per reinem Datums-PUT umgehen.
    _times_affected = entry_data.date is not None
    if entry_data.date is not None:
        entry.date = entry_data.date
    if entry_data.start_time is not None or _times_affected:
        entry.start_time = eff_start
    if entry_data.end_time is not None or _times_affected:
        entry.end_time = eff_end
    if entry_data.break_minutes is not None:
        entry.break_minutes = entry_data.break_minutes
    if entry_data.note is not None:
        entry.note = entry_data.note
    # M-ARB3: persist the documented §4 break waiver when one was supplied.
    if break_waiver_active:
        entry.break_waiver_reason = waiver_reason
    # #201: raw_* — reset to None when not capped, set when capped.
    # Only update raw_* when start_time or end_time was explicitly provided in the request.
    if entry_data.start_time is not None or _times_affected:
        entry.raw_start_time = raw_start
    if entry_data.end_time is not None or _times_affected:
        entry.raw_end_time = raw_end

    db.commit()
    db.refresh(entry)

    response = TimeEntryResponse.model_validate(entry)
    response.warnings = admin_update_warnings
    return response


@router.delete("/time-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_time_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin deletes a time entry with audit logging."""
    # F-026: explicit tenant scope so a guessed UUID from another tenant 404s.
    # F-028/S-M04: lock the row so a concurrent edit/delete can't race between
    # the lookup and the db.delete() below. Mirrors admin_update_time_entry.
    entry = (
        db.query(TimeEntry)
        .filter(
            TimeEntry.id == entry_id,
            TimeEntry.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    _create_audit_log(
        db, entry.id, entry.user_id, current_user.id,
        action="delete", old_entry=entry, source="manual",
        tenant_id=current_user.tenant_id,
    )

    db.delete(entry)
    db.commit()
    return None


# ── Audit Log ────────────────────────────────────────────────────────────

@router.get("/audit-log", response_model=List[AuditLogResponse])
def list_audit_log(
    user_id: Optional[str] = Query(None, description="Filter by affected user"),
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    before: Optional[str] = Query(
        None,
        description="Keyset cursor — ISO-8601 timestamp; return entries strictly older than this",
    ),
    before_id: Optional[str] = Query(
        None,
        description="Keyset-Tiebreaker — id der letzten Zeile; nötig, weil created_at "
        "(func.now() = Transaktionszeit) bei Bulk-Inserts mehrfach identisch ist (ADM-12).",
    ),
    changes_only: bool = Query(
        False,
        description="Return only real change actions (create/update/delete), "
        "excluding access/system events such as DSGVO read-access markers (#284).",
    ),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    List audit log entries.

    F-054: Supports two pagination modes — cursor-based (preferred) and
    offset-based (legacy). The audit log grows indefinitely; OFFSET N on
    a table with 100k+ rows forces Postgres to materialise and discard N
    rows on every page load, so the admin UI should switch to the
    ``before`` cursor ASAP. Pass the ``created_at`` of the last row from
    the previous page as ``before`` to fetch the next older page.
    """
    # F-026: explicit tenant scoping on top of RLS — the audit log carries the
    # most sensitive cross-tenant data (old/new note text, user ids).
    query = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == current_user.tenant_id
    )

    if user_id:
        query = query.filter(TimeEntryAuditLog.user_id == user_id)

    if changes_only:
        # #284: keep the per-employee change log free of access/system events.
        query = query.filter(TimeEntryAuditLog.action.in_(_CHANGE_ACTIONS))

    if month:
        try:
            year, month_num = map(int, month.split('-'))
            query = query.filter(
                date_in_month(TimeEntryAuditLog.created_at, year, month_num),
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if before:
        # Keyset pagination: skip OFFSET entirely, use a strict ``<`` on
        # the indexed created_at column.
        try:
            from datetime import datetime as _dt
            before_ts = _dt.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Ungültiges 'before' Format (ISO-8601 erwartet)",
            )
        # ADM-12: created_at allein ist KEIN eindeutiger Cursor — func.now() ist die
        # Transaktionszeit, also tragen alle Audit-Rows EINER Transaktion (Bulk-Import,
        # Betriebsferien, Jahresabschluss) denselben Timestamp. Ein striktes `< ts`
        # würde an der Seitengrenze die restliche Gleichstands-Gruppe still verschlucken.
        # Daher Komposit-Keyset (created_at, id) mit stabilem Sekundärsort.
        if before_id:
            query = query.filter(
                or_(
                    TimeEntryAuditLog.created_at < before_ts,
                    and_(
                        TimeEntryAuditLog.created_at == before_ts,
                        TimeEntryAuditLog.id < before_id,
                    ),
                )
            )
        else:
            query = query.filter(TimeEntryAuditLog.created_at < before_ts)
        logs = (
            query.order_by(
                TimeEntryAuditLog.created_at.desc(), TimeEntryAuditLog.id.desc()
            )
            .limit(limit)
            .all()
        )
    else:
        # Legacy offset-based path — kept for backward compatibility with
        # the current frontend. Grows linearly with page index, deprecated
        # once the UI switches to 'before'.
        logs = (
            query.order_by(
                TimeEntryAuditLog.created_at.desc(), TimeEntryAuditLog.id.desc()
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    # #431 / Art. 5(2) + Art. 9: Admin-Lesezugriff auf das Protokoll einer
    # FREMDEN Person vermerken. Diese Fläche zeigt seit #431 ``old_note``/
    # ``new_note`` an, und die Rückrechnung nach einer Wochenstunden-Änderung
    # schreibt dort je nachgezogener Abwesenheit deutschen Klartext
    # („Krank 8,0 h"). Damit sieht ein Admin hier dieselben Gesundheitsdaten
    # wie über Abwesenheitsliste, Journal und Berichte — die alle
    # protokollieren; nur diese Fläche tat es nicht.
    #
    # ⚠️ ANDERS als absences.py (Vorbild): dort wird JEDER gezielte Zugriff
    # vermerkt, weil die Spur am Zugriff hängt und ``Absence`` eine andere
    # Tabelle als das eigene Protokoll ist — kein Feedback-Loop. Hier läuft
    # die Vermerk-Zeile in ``time_entry_audit_logs`` ein, also GENAU in die
    # Tabelle, die dieser Endpoint selbst auflistet: ein Vermerk pro Aufruf
    # (jeder Seitenaufruf, MA-/Monatswechsel, "Mehr laden") würde beim
    # nächsten Aufruf oben in derselben Liste stehen und echte Änderungen
    # Richtung Seitenlimit verdrängen (Fund Fix-Welle 4 #2). Der Zweck des
    # Vermerks ist der Nachweis „wer hat wann fremde GESUNDHEITSDATEN
    # eingesehen" — ein Aufruf ohne sensiblen Inhalt in der Antwort ist kein
    # solcher Zugriff. Deshalb wird NUR geschrieben, wenn ``sensitive`` True
    # ist (action ist dann immer ``health_data_read``, nie ``audit_log_read``
    # — der zweite Marker existiert nur für ältere, vor diesem Fix
    # geschriebene Zeilen). NICHT „konsistent zu absences.py" zurückbauen.
    if user_id and str(user_id) != str(current_user.id):
        sensitive = any(_audit_note_is_health_sensitive(log) for log in logs)
        if sensitive:
            db.add(TimeEntryAuditLog(
                time_entry_id=None,
                user_id=user_id,
                changed_by=current_user.id,
                action="health_data_read",
                new_note="Admin-Lesezugriff auf fremdes Änderungsprotokoll inkl. Gesundheitsdaten",
                source="dsgvo",
                tenant_id=current_user.tenant_id,
            ))
            db.commit()

    return _enrich_audit_responses(logs, db)


@router.get("/audit/verify-integrity")
def verify_audit_integrity(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """#121: Tamper-Evidence-Check aller Audit-Rows des Tenants.

    Berechnet pro Row den HMAC neu (Schluessel aus SECRET_KEY abgeleitet) und
    vergleicht ihn mit dem gespeicherten ``row_hash``. Eine nachtraegliche
    Manipulation einer Audit-Row (z. B. via SQL-Injection an anderer Stelle)
    bricht den Hash -> ``tampered``. Vor dem Feature geschriebene Rows ohne Hash
    sind ``legacy_unhashed`` (nicht verifizierbar, NICHT als Manipulation
    gewertet). ``intact`` ist true, wenn keine gehashte Row manipuliert wurde.
    """
    from app.core import audit_integrity

    checked = ok = tampered = legacy = 0
    tampered_ids: list[str] = []
    # F-026: explizit auf den Tenant scopen (zusaetzlich zu RLS). yield_per haelt
    # den Speicher bei sehr grossen Audit-Tabellen klein.
    rows = (
        db.query(TimeEntryAuditLog)
        .filter(TimeEntryAuditLog.tenant_id == current_user.tenant_id)
        .yield_per(500)
    )
    for row in rows:
        checked += 1
        if not row.row_hash:
            legacy += 1
        elif audit_integrity.verify_row(row):
            ok += 1
        else:
            tampered += 1
            if len(tampered_ids) < 100:  # Antwort begrenzen
                tampered_ids.append(str(row.id))

    return {
        "checked": checked,
        "ok": ok,
        "tampered": tampered,
        "legacy_unhashed": legacy,
        "intact": tampered == 0,
        "tampered_ids": tampered_ids,
    }
