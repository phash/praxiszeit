from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.services.date_filters import date_in_year, date_in_month
from sqlalchemy import extract
from typing import List, Optional
from datetime import datetime, date, time, timezone
from app.services.timezone_service import LOCAL_TZ, now_local as _now_local, today_local as _today_local
from app.database import get_db
from app.models import (
    User, TimeEntry, UserRole, TimeEntryAuditLog,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.services import settings_service, milog_service
from app.middleware.auth import get_current_user
from app.schemas.time_entry import (
    TimeEntryCreate, TimeEntryUpdate, TimeEntryResponse,
    ClockInRequest, ClockOutRequest, ClockStatusResponse,
)
from app.services.holiday_service import is_holiday
from app.services.break_validation_service import validate_daily_break
from app.services.arbzg_utils import is_night_work, NIGHT_THRESHOLD_MINUTES
from app.routers.admin_helpers import _create_audit_log
from uuid import UUID as UUIDType

router = APIRouter(prefix="/api/time-entries", tags=["time-entries"])


# #144 §4 ArbZG: audit-log source marker for a documented break waiver.
# Must stay < 40 chars (time_entry_audit_logs.source is varchar(40)).
BREAK_WAIVER_SOURCE = "break_waiver"  # 12 chars


def _break_exception_requires_approval(db: Session, tenant_id) -> bool:
    """Read the per-practice toggle whether break-waivers need admin approval."""
    return settings_service.get_bool_setting(
        db, "break_exception_requires_approval", tenant_id=tenant_id
    )


MAX_DAILY_HOURS_HARD = 10.0         # §3 ArbZG: absolute Obergrenze
MAX_DAILY_HOURS_WARN = 8.0          # §3 ArbZG: Regelgrenze (Warnung)
MAX_WEEKLY_HOURS_WARN = 48.0        # §3 ArbZG: 6 Werktage × 8h Durchschnitt = 48h/Woche
MAX_NIGHT_WORKER_DAILY_WARN = 8.0   # §6 Abs. 2 ArbZG: Tageslimit für Nachtarbeitnehmer


def _net_hours(st: time, et: time, brk: int) -> float:
    """Calculate net working hours from start/end time and break minutes.

    Invariant: et > st. This is NOT over-midnight aware on purpose — the system
    models over-midnight shifts as two separate entries, and end<=start is
    rejected on every write path (schema + router validation; the XLS importer
    skips such rows in execute_import). Reinterpreting et<st as "+1 day" would
    silently turn a data-entry error (e.g. swapped start/end) into a 16h shift,
    so we keep the max(0, …) floor as a last-resort guard instead.
    """
    mins = (et.hour * 60 + et.minute) - (st.hour * 60 + st.minute)
    return max(0.0, (mins - brk) / 60.0)


def _calculate_daily_net_hours(
    db: Session,
    user_id: UUIDType,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    exclude_entry_id=None,
    tenant_id=None,
) -> float:
    """Sum up all net hours for a user on a given date, including the new/updated entry."""
    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.date == entry_date,
        TimeEntry.end_time.isnot(None),
    )
    # F-026: expliziter Tenant-Filter zusätzlich zu RLS (belt-and-suspenders).
    if tenant_id is not None:
        query = query.filter(TimeEntry.tenant_id == tenant_id)
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    existing = query.all()

    total = sum(_net_hours(e.start_time, e.end_time, e.break_minutes) for e in existing)
    total += _net_hours(start_time, end_time, break_minutes)
    return total


def _calculate_weekly_net_hours(
    db: Session,
    user_id: UUIDType,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    exclude_entry_id=None,
    tenant_id=None,
) -> float:
    """Sum all net hours for the ISO calendar week containing entry_date, including the new/updated entry."""
    from datetime import timedelta
    # Monday of that ISO week
    monday = entry_date - timedelta(days=entry_date.weekday())
    sunday = monday + timedelta(days=6)

    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.date >= monday,
        TimeEntry.date <= sunday,
        TimeEntry.end_time.isnot(None),
    )
    # F-026: expliziter Tenant-Filter zusätzlich zu RLS (belt-and-suspenders).
    if tenant_id is not None:
        query = query.filter(TimeEntry.tenant_id == tenant_id)
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    existing = query.all()

    total = sum(_net_hours(e.start_time, e.end_time, e.break_minutes) for e in existing)
    total += _net_hours(start_time, end_time, break_minutes)
    return total



def _enrich_response(
    response: "TimeEntryResponse",
    entry: TimeEntry,
    current_user: User,
    db: Session,
    warnings: "list[str] | None" = None,
) -> "TimeEntryResponse":
    """Set computed fields on a TimeEntryResponse."""
    response.is_editable = _compute_is_editable(entry, current_user)
    weekday = entry.date.weekday()
    holiday = is_holiday(db, entry.date, tenant_id=current_user.tenant_id)
    response.is_sunday_or_holiday = weekday == 6 or bool(holiday)
    response.is_night_work = (
        is_night_work(entry.start_time, entry.end_time)
        if entry.end_time else False
    )
    response.warnings = warnings or []
    return response


def _compute_is_editable(entry: TimeEntry, current_user: User) -> bool:
    """Check if a time entry is editable by the current user."""
    if current_user.role == UserRole.ADMIN:
        return True
    return entry.date == _today_local()


def _get_open_entry(db: Session, user_id, with_lock: bool = False, tenant_id=None) -> Optional[TimeEntry]:
    """Find an open (clocked-in, no end_time) entry for the user."""
    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.end_time.is_(None),
    )
    # F-026: expliziter Tenant-Filter zusätzlich zu RLS (belt-and-suspenders) —
    # dieser Lookup liegt im Clock-in/out-Schreibpfad.
    if tenant_id is not None:
        query = query.filter(TimeEntry.tenant_id == tenant_id)
    if with_lock:
        query = query.with_for_update()
    return query.first()


def _close_stale_entry(
    db: Session,
    entry: TimeEntry,
    *,
    changed_by_id=None,
) -> None:
    """Close a stale open entry at 23:59 of its date.

    F-043: Does NOT commit — the caller's transaction owns the commit.
    Writes a TimeEntryAuditLog row with action=update / source=auto_close
    so stale auto-closes can be traced and so §3 ArbZG violations on
    previous days are not silently lost.
    """
    old_end_time = entry.end_time
    old_note = entry.note

    entry.end_time = time(23, 59)
    entry.note = (entry.note or '') + ' [auto-closed]'
    if entry.note.startswith(' '):
        entry.note = entry.note.strip()

    audit = TimeEntryAuditLog(
        time_entry_id=entry.id,
        user_id=entry.user_id,
        changed_by=changed_by_id or entry.user_id,
        action="update",
        source="auto_close",
        old_date=entry.date,
        old_start_time=entry.start_time,
        old_end_time=old_end_time,
        old_break_minutes=entry.break_minutes,
        old_note=old_note,
        new_date=entry.date,
        new_start_time=entry.start_time,
        new_end_time=entry.end_time,
        new_break_minutes=entry.break_minutes,
        new_note=entry.note,
        tenant_id=entry.tenant_id,
    )
    db.add(audit)
    db.flush()


# --- Clock endpoints (must be BEFORE /{entry_id} to avoid route conflicts) ---

@router.get("/clock-status", response_model=ClockStatusResponse)
def get_clock_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current clock-in/out status for the authenticated user."""
    open_entry = _get_open_entry(db, current_user.id, tenant_id=current_user.tenant_id)

    if not open_entry:
        return ClockStatusResponse(is_clocked_in=False)

    # If the open entry is from a previous day, auto-close it
    if open_entry.date != _today_local():
        _close_stale_entry(db, open_entry, changed_by_id=current_user.id)
        db.commit()  # F-043: /clock-status now owns the commit
        return ClockStatusResponse(is_clocked_in=False)

    # Calculate elapsed minutes in local time
    now = _now_local()
    start_dt = datetime.combine(open_entry.date, open_entry.start_time, tzinfo=LOCAL_TZ)
    elapsed = int((now - start_dt).total_seconds() / 60)

    response_entry = TimeEntryResponse.model_validate(open_entry)
    _enrich_response(response_entry, open_entry, current_user, db)

    return ClockStatusResponse(
        is_clocked_in=True,
        current_entry=response_entry,
        elapsed_minutes=elapsed,
    )


@router.post("/clock-in", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def clock_in(
    body: ClockInRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clock in: create a time entry with start_time=now, end_time=NULL."""
    # VULN-009: use SELECT FOR UPDATE to prevent race condition on concurrent clock-in
    open_entry = _get_open_entry(db, current_user.id, with_lock=True, tenant_id=current_user.tenant_id)
    if open_entry:
        if open_entry.date != _today_local():
            # Stale entry from a previous day: auto-close in the same
            # transaction as the new clock-in. F-043: no intermediate
            # commit, so the row-lock held by _get_open_entry stays alive
            # until the new entry is persisted.
            _close_stale_entry(db, open_entry, changed_by_id=current_user.id)
        else:
            raise HTTPException(
                status_code=400,
                detail="Bereits eingestempelt. Bitte zuerst ausstempeln.",
            )

    now = _now_local()

    # Check first/last work day
    if current_user.first_work_day and now.date() < current_user.first_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
    if current_user.last_work_day and now.date() > current_user.last_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")

    # #201: clamp early start to [soll_start − grace]; preserve raw stamp.
    from app.services import work_window_service
    grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    start_t = now.time().replace(second=0, microsecond=0)
    eff_start, _eff_end, raw_start, _raw_end = work_window_service.clamp(
        current_user, now.date(), start_t, None, grace,
    )

    entry = TimeEntry(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        date=now.date(),
        start_time=eff_start,
        raw_start_time=raw_start,
        end_time=None,
        break_minutes=0,
        note=body.note,
    )

    # §5 ArbZG: Ruhezeit-Warnung (11h seit letztem Arbeitsende)
    clock_in_warnings: list[str] = []
    if raw_start is not None:
        clock_in_warnings.append(
            f"EARLY_START: Du hast vor deinem Soll-Beginn eingestempelt — angerechnet ab {eff_start.strftime('%H:%M')}."
        )
    if not current_user.exempt_from_arbzg:
        last_entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.tenant_id == current_user.tenant_id,  # F-026
            TimeEntry.end_time.isnot(None),
            # MZ-01: nur Einträge VOR HEUTE — §5 ist die Ruhezeit ZWISCHEN
            # Arbeitstagen. Ein früherer ausgestempelter Eintrag am selben Tag
            # (geteilte Sprechzeit: vormittags aus, nachmittags wieder ein) ist
            # eine Pause innerhalb des Arbeitstags (§4), keine §5-Ruhezeit — sonst
            # feuert die Warnung beim 2. Einstempeln fälschlich.
            TimeEntry.date < now.date(),
        ).order_by(TimeEntry.date.desc(), TimeEntry.end_time.desc()).first()

        if last_entry:
            # F-030: Build both datetimes as TZ-aware in Europe/Berlin so
            # that DST transitions (spring-forward / fall-back) yield the
            # correct wall-clock gap. Using naive combine() was numerically
            # right in 51 weeks/year but off by 1h during the DST weekend —
            # the §5 warning would fire or not fire incorrectly.
            # §5 misst die TATSÄCHLICHE Anwesenheit → Rohstempel (#201), nicht die
            # work-window-gekappten Zeiten (sonst wird die Lücke zu groß gerechnet
            # und ein echter Verstoß bleibt unentdeckt). Fallback auf die gekappten.
            last_end = datetime.combine(
                last_entry.date, last_entry.raw_end_time or last_entry.end_time, tzinfo=LOCAL_TZ
            )
            current_start = datetime.combine(
                now.date(), entry.raw_start_time or entry.start_time, tzinfo=LOCAL_TZ
            )
            rest_hours = (current_start - last_end).total_seconds() / 3600
            if rest_hours < 11:
                clock_in_warnings.append(f"REST_TIME_WARNING: Nur {rest_hours:.1f}h Ruhezeit seit letztem Arbeitsende (Minimum: 11h, §5 ArbZG)")

    db.add(entry)
    db.commit()
    db.refresh(entry)

    response = TimeEntryResponse.model_validate(entry)
    response.is_editable = True
    response.warnings = clock_in_warnings
    return response


@router.post("/clock-out", response_model=TimeEntryResponse)
def clock_out(
    body: ClockOutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clock out: set end_time=now and break_minutes on the open entry."""
    open_entry = _get_open_entry(db, current_user.id, with_lock=True, tenant_id=current_user.tenant_id)

    if not open_entry:
        raise HTTPException(
            status_code=400,
            detail="Nicht eingestempelt. Bitte zuerst einstempeln.",
        )

    # If stale entry from a previous day, auto-close and error
    if open_entry.date != _today_local():
        _close_stale_entry(db, open_entry, changed_by_id=current_user.id)
        # B-H1: commit the auto-close BEFORE raising. get_db only commits on a
        # successful return — raising here would otherwise roll back the
        # end_time + audit row, leaving the stale entry open forever.
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Offener Eintrag von einem früheren Tag wurde automatisch geschlossen. Bitte neu einstempeln.",
        )

    now = _now_local()
    new_end_time = now.time().replace(second=0, microsecond=0)
    exempt = current_user.exempt_from_arbzg

    # #201: clamp late end to [soll_end + grace]; preserve raw stamp.
    from app.services import work_window_service
    grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    _eff_start, eff_end, _raw_start, raw_end = work_window_service.clamp(
        current_user, open_entry.date, open_entry.start_time, new_end_time, grace,
    )

    # §3 ArbZG: check daily hours before committing – skipped for exempt users
    daily_hours = _calculate_daily_net_hours(
        db=db,
        user_id=current_user.id,
        entry_date=open_entry.date,
        start_time=open_entry.start_time,
        end_time=eff_end,
        break_minutes=body.break_minutes,
        exclude_entry_id=open_entry.id,
        tenant_id=current_user.tenant_id,
    )
    # Review R2-b: §3 ArbZG (10h-Höchstgrenze) darf das Ausstempeln NICHT mit
    # 422 blockieren. Die Arbeitszeit IST zum Ausstempel-Zeitpunkt bereits
    # geleistet — ein 422 ließe (über das get_db-Rollback) den offenen Eintrag
    # ohne end_time zurück, sodass der MA dauerhaft eingestempelt bleibt und
    # jeder Ausstempel-Versuch erneut 422t. Stattdessen wird der Eintrag
    # wahrheitsgemäß geschlossen (§16-Nachweis) und der §3-Verstoß weiter unten
    # als deutliche Warnung ausgegeben — analog zur nicht-blockierenden
    # §4-Pausen-Prüfung. Die harte 422-Sperre bleibt an den Pfaden mit frei
    # wählbaren Zeiten (manueller Eintrag, Antrag) bestehen, wo der Nutzer
    # die Zeiten vor dem Speichern korrigieren kann.

    open_entry.end_time = eff_end
    open_entry.raw_end_time = raw_end
    open_entry.break_minutes = body.break_minutes
    if body.note:
        open_entry.note = body.note

    db.commit()
    db.refresh(open_entry)

    # H-2 (§16 ArbZG / EuGH C-55/18, Review 2026-06-23): jeden normalen
    # Ausstempelvorgang protokollieren — bisher nur bei break_waiver. Ohne Audit
    # zeigte ein spaeteres Admin-Edit als "original" die Admin-gesetzte Zeit statt
    # des echten Stempelzeitpunkts. Quelle 'clock_out' (<= varchar(40)).
    _create_audit_log(
        db,
        open_entry.id,
        open_entry.user_id,
        current_user.id,
        action="update",
        new_entry=open_entry,
        source="clock_out",
        tenant_id=current_user.tenant_id,
    )
    db.commit()
    db.refresh(open_entry)

    clock_out_warnings: list[str] = []
    if not exempt:
        # ArbZG §4: break validation (warning only, don't block clock-out)
        break_error = validate_daily_break(
            db=db,
            user_id=current_user.id,
            entry_date=open_entry.date,
            start_time=open_entry.start_time,
            end_time=eff_end,
            break_minutes=body.break_minutes,
            exclude_entry_id=open_entry.id,
        )
        if break_error:
            # M-ARB1: if the employee supplied a break_waiver_reason, document the
            # §4 deviation on the entry + audit trail (source='break_waiver'),
            # mirroring the create/CR paths (#144). Clock-out stays non-blocking
            # either way — without a reason it is a plain warning as before.
            waiver_reason = (body.break_waiver_reason or "").strip()
            if waiver_reason:
                open_entry.break_waiver_reason = waiver_reason
                _create_audit_log(
                    db,
                    open_entry.id,
                    open_entry.user_id,
                    current_user.id,
                    action="update",
                    new_entry=open_entry,
                    source=BREAK_WAIVER_SOURCE,
                    tenant_id=current_user.tenant_id,
                )
                db.commit()
                db.refresh(open_entry)
                clock_out_warnings.append(f"BREAK_WAIVER: {break_error}")
            else:
                clock_out_warnings.append(f"BREAK_WARNING: {break_error}")
    if not exempt:
        if daily_hours > MAX_DAILY_HOURS_HARD:
            # Review R2-b: §3-Höchstgrenze überschritten — der Eintrag wurde
            # geschlossen (nicht blockiert), der Verstoß wird hier deutlich
            # gemeldet, damit er sichtbar/auditierbar bleibt.
            clock_out_warnings.append(
                f"DAILY_HOURS_HARD: Tagesarbeitszeit beträgt {daily_hours:.1f}h und "
                f"überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG)."
            )
        elif daily_hours > MAX_DAILY_HOURS_WARN:
            clock_out_warnings.append("DAILY_HOURS_WARNING")
        weekly_hours_out = _calculate_weekly_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=open_entry.date,
            start_time=open_entry.start_time,
            end_time=eff_end,
            break_minutes=body.break_minutes,
            exclude_entry_id=open_entry.id,
            tenant_id=current_user.tenant_id,
        )
        if weekly_hours_out > MAX_WEEKLY_HOURS_WARN:
            clock_out_warnings.append("WEEKLY_HOURS_WARNING")
        if open_entry.date.weekday() == 6:
            clock_out_warnings.append("SUNDAY_WORK")
        if is_holiday(db, open_entry.date, tenant_id=current_user.tenant_id):
            clock_out_warnings.append("HOLIDAY_WORK")
        if (
            current_user.is_night_worker
            and is_night_work(open_entry.start_time, eff_end)
            and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            clock_out_warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    # #377 § 2 Abs. 2 MiLoG: weiche Warnung, wenn die Konto-Plusstunden dieses
    # Monats (month-to-date, inkl. des eben geschlossenen Eintrags) 50 % der
    # vereinbarten Monatszeit reißen. Unabhängig von `exempt` (keine ArbZG-§18-Frage).
    if current_user.milog_working_time_account:
        _m = milog_service.milog_50_check(
            db, current_user, open_entry.date.year, open_entry.date.month, up_to_date=open_entry.date)
        if _m:
            clock_out_warnings.append(milog_service.milog_50_warning_text(_m))
        # #377 Baustein 2b: weiche Plausibilitäts-Warnung für Fix-Modus-MA.
        _mx = milog_service.monthly_exceeded_check(
            db, current_user, open_entry.date.year, open_entry.date.month, up_to_date=open_entry.date)
        if _mx:
            clock_out_warnings.append(milog_service.monthly_exceeded_warning_text(_mx))

    response = TimeEntryResponse.model_validate(open_entry)
    _enrich_response(response, open_entry, current_user, db, warnings=clock_out_warnings)
    return response


# --- Standard CRUD endpoints ---

@router.get("/", response_model=List[TimeEntryResponse])
def list_time_entries(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List time entries.
    Regular users can only see their own entries.
    Admins can filter by user_id.
    """
    # F-026: expliziter Tenant-Filter zusätzlich zu RLS
    query = db.query(TimeEntry).filter(TimeEntry.tenant_id == current_user.tenant_id)

    # If user_id is provided, only admin can filter by it
    if user_id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
        query = query.filter(TimeEntry.user_id == user_id)
    else:
        # Regular users only see their own entries
        query = query.filter(TimeEntry.user_id == current_user.id)

    # Filter by month if provided
    if month:
        try:
            year, month_num = map(int, month.split('-'))
            query = query.filter(
                date_in_month(TimeEntry.date, year, month_num)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    entries = query.order_by(
        TimeEntry.date.desc(), TimeEntry.start_time.desc()
    ).offset(skip).limit(limit).all()

    results = []
    for entry in entries:
        response = TimeEntryResponse.model_validate(entry)
        _enrich_response(response, entry, current_user, db)
        results.append(response)

    return results


@router.get("/{entry_id}", response_model=TimeEntryResponse)
def get_time_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific time entry."""
    entry = db.query(TimeEntry).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Check permissions
    if entry.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        # #120 (Review 2026-06-23): 404 statt 403 — ein fremder Same-Tenant-Eintrag
        # wird wie ein unbekannter behandelt (kein Existenz-Leak via Response-Code).
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")

    response = TimeEntryResponse.model_validate(entry)
    _enrich_response(response, entry, current_user, db)
    return response


@router.post("/", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def create_time_entry(
    entry_data: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new time entry."""

    # Edit protection: employees can only create entries for today
    if current_user.role != UserRole.ADMIN and entry_data.date != _today_local():
        raise HTTPException(
            status_code=403,
            detail="Einträge für vergangene Tage können nur per Änderungsantrag erstellt werden"
        )

    # Check first/last work day
    if current_user.first_work_day and entry_data.date < current_user.first_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
    if current_user.last_work_day and entry_data.date > current_user.last_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")

    # Check for overlapping entries on the same date
    existing = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
        TimeEntry.date == entry_data.date,
        TimeEntry.start_time == entry_data.start_time
    ).first()

    if existing:
        # B-L4: duplicate entry is a conflict, not a bad request — align with
        # the 409 used by the CR-approval and absence duplicate paths.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es existiert bereits ein Eintrag mit dieser Startzeit an diesem Datum"
        )

    exempt = current_user.exempt_from_arbzg

    # #201: clamp start/end to [soll − grace, soll + grace] BEFORE all §4/§3
    # checks so that compliance is assessed on the credited (angerechnete) time,
    # not on the raw input. raw_* store the original stamp when clamping occurs.
    from app.services import work_window_service
    _grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(
        current_user, entry_data.date, entry_data.start_time, entry_data.end_time, _grace,
    )

    # §3 ArbZG: daily hours hard cap – skipped for exempt users.
    # MUST run BEFORE the §4 break-waiver / approval branch below: a >10h day is
    # an absolute legal ceiling that no break waiver (and no approval workflow)
    # can lift. Computing + raising here ensures the entry is rejected regardless
    # of whether the practice requires approval for break exceptions (#144 fix).
    daily_hours = _calculate_daily_net_hours(
        db=db,
        user_id=current_user.id,
        entry_date=entry_data.date,
        start_time=eff_start,
        end_time=eff_end,
        break_minutes=entry_data.break_minutes,
        tenant_id=current_user.tenant_id,
    )
    if not exempt and daily_hours > MAX_DAILY_HOURS_HARD:
        raise HTTPException(
            status_code=422,
            detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG)."
        )

    # #144 §4 ArbZG: a documented exception when the mandatory break was not
    # possible. Only for non-exempt users (exempt skip §4 entirely, #141).
    waiver_reason = (entry_data.break_waiver_reason or "").strip()
    break_waiver_active = False  # set True once a valid waiver overrides §4

    # Break validation (ArbZG §4) – skipped for exempt users
    if not exempt:
        break_error = validate_daily_break(
            db=db,
            user_id=current_user.id,
            entry_date=entry_data.date,
            start_time=eff_start,
            end_time=eff_end,
            break_minutes=entry_data.break_minutes,
        )
        if break_error:
            if not waiver_reason:
                # No documented exception → the §4 block stands (unchanged).
                raise HTTPException(status_code=400, detail=break_error)

            # A valid waiver was supplied. If the practice requires approval,
            # do NOT write the entry — file a ChangeRequest (request_type=CREATE)
            # that materialises the entry (with break_waiver_reason) on approval.
            # §16/#201: store the employee's RAW (un-clamped) times in the CR.
            # The clamp is applied once, at approval (admin_change_requests), which
            # derives entry.raw_start/raw_end from these raw values. Storing the
            # already-clamped time here would make the approval-time clamp a no-op
            # (raw_* = None) and permanently lose the original stamp (§16 ArbZG).
            if _break_exception_requires_approval(db, current_user.tenant_id):
                cr = ChangeRequest(
                    user_id=current_user.id,
                    tenant_id=current_user.tenant_id,
                    request_type=ChangeRequestType.CREATE,
                    entry_kind="time_entry",
                    status=ChangeRequestStatus.PENDING,
                    proposed_date=entry_data.date,
                    proposed_start_time=entry_data.start_time,
                    proposed_end_time=entry_data.end_time,
                    proposed_break_minutes=entry_data.break_minutes,
                    proposed_note=entry_data.note,
                    reason=waiver_reason,
                    break_waiver_reason=waiver_reason,
                )
                db.add(cr)
                db.commit()
                db.refresh(cr)
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "status": "pending_approval",
                        "change_request_id": str(cr.id),
                        "detail": (
                            "Pflicht-Pause-Ausnahme zur Genehmigung eingereicht. "
                            "Der Eintrag wird nach Admin-Freigabe wirksam."
                        ),
                        "warnings": [f"BREAK_WAIVER_PENDING: {break_error}"],
                    },
                )

            # No approval required → persist the entry with the waiver reason
            # and surface the §4 deviation as a warning.
            break_waiver_active = True

    # Collect warnings (also skipped for exempt users)
    warnings: list[str] = []
    if break_waiver_active:
        # Re-run validation to surface the concrete §4 detail in the warning.
        waiver_detail = validate_daily_break(
            db=db,
            user_id=current_user.id,
            entry_date=entry_data.date,
            start_time=eff_start,
            end_time=eff_end,
            break_minutes=entry_data.break_minutes,
        )
        warnings.append(f"BREAK_WAIVER: {waiver_detail}")
    if not exempt:
        if daily_hours > MAX_DAILY_HOURS_WARN:
            warnings.append("DAILY_HOURS_WARNING")
        weekly_hours = _calculate_weekly_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=entry_data.date,
            start_time=eff_start,
            end_time=eff_end,
            break_minutes=entry_data.break_minutes,
            tenant_id=current_user.tenant_id,
        )
        if weekly_hours > MAX_WEEKLY_HOURS_WARN:
            warnings.append("WEEKLY_HOURS_WARNING")
        weekday = entry_data.date.weekday()
        is_sunday = weekday == 6
        holiday = is_holiday(db, entry_data.date, tenant_id=current_user.tenant_id)
        if is_sunday:
            warnings.append("SUNDAY_WORK")
        if holiday:
            warnings.append("HOLIDAY_WORK")
        if (
            current_user.is_night_worker
            and is_night_work(eff_start, eff_end)
            and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    # Create entry with clamped times; raw_* capture the original input when clamped.
    entry = TimeEntry(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        date=entry_data.date,
        start_time=eff_start,
        end_time=eff_end,
        raw_start_time=raw_start,
        raw_end_time=raw_end,
        break_minutes=entry_data.break_minutes,
        note=entry_data.note,
        sunday_exception_reason=entry_data.sunday_exception_reason,
        break_waiver_reason=waiver_reason if break_waiver_active else None,
    )

    db.add(entry)

    # #144 §4 ArbZG: leave an audit trail for the documented break waiver so the
    # deviation is traceable (source marker 'break_waiver', < 40 chars).
    if break_waiver_active:
        db.flush()
        _create_audit_log(
            db,
            entry.id,
            entry.user_id,
            current_user.id,
            action="create",
            new_entry=entry,
            source=BREAK_WAIVER_SOURCE,
            tenant_id=current_user.tenant_id,
        )

    db.commit()
    db.refresh(entry)

    # #377 § 2 Abs. 2 MiLoG: manuell buchende Minijobber erreichen clock_out nie —
    # daher auch hier die weiche 50-%-Warnung (month-to-date inkl. dieses Eintrags).
    if current_user.milog_working_time_account:
        _m = milog_service.milog_50_check(
            db, current_user, entry.date.year, entry.date.month, up_to_date=entry.date)
        if _m:
            warnings.append(milog_service.milog_50_warning_text(_m))
        # #377 Baustein 2b: weiche Plausibilitäts-Warnung für Fix-Modus-MA.
        _mx = milog_service.monthly_exceeded_check(
            db, current_user, entry.date.year, entry.date.month, up_to_date=entry.date)
        if _mx:
            warnings.append(milog_service.monthly_exceeded_warning_text(_mx))

    response = TimeEntryResponse.model_validate(entry)
    _enrich_response(response, entry, current_user, db, warnings=warnings)
    return response


@router.put("/{entry_id}", response_model=TimeEntryResponse)
def update_time_entry(
    entry_id: str,
    entry_data: TimeEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a time entry."""
    entry = db.query(TimeEntry).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Check permissions
    if entry.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        # #120 (Review 2026-06-23): 404 statt 403 — ein fremder Same-Tenant-Eintrag
        # wird wie ein unbekannter behandelt (kein Existenz-Leak via Response-Code).
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")

    # Edit protection: employees can only edit today's entries
    if current_user.role != UserRole.ADMIN and entry.date != _today_local():
        raise HTTPException(
            status_code=403,
            detail="Einträge vergangener Tage können nur per Änderungsantrag geändert werden"
        )

    # #144: snapshot the persisted values BEFORE mutating in-memory, so an
    # approval-required waiver can file an UPDATE ChangeRequest against the
    # unchanged entry without first committing the edit.
    orig_snapshot = {
        "date": entry.date,
        "start_time": entry.start_time,
        "end_time": entry.end_time,
        "break_minutes": entry.break_minutes,
        "note": entry.note,
        # §16: keep the persisted raw stamp so an approval-required waiver CR
        # can preserve it when start/end are not part of this partial update.
        "raw_start_time": entry.raw_start_time,
        "raw_end_time": entry.raw_end_time,
    }

    # Update fields
    update_data = entry_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    # Validate end_time > start_time (only if both are set)
    if entry.end_time is not None and entry.end_time <= entry.start_time:
        raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

    # §16/#201: snapshot the employee's intended RAW times BEFORE the clamp below
    # overwrites entry.start/end with credited time. An approval-required waiver
    # CR (further down) must carry these raw values so the clamp at approval can
    # reconstruct raw_start/raw_end. If start/end were not part of this partial
    # update, fall back to the entry's existing raw stamp (or its start/end).
    _intended_start = (
        entry.start_time if "start_time" in update_data
        else (orig_snapshot["raw_start_time"] or orig_snapshot["start_time"])
    )
    _intended_end = (
        entry.end_time if "end_time" in update_data
        else (orig_snapshot["raw_end_time"] or orig_snapshot["end_time"])
    )

    # #201: clamp start/end to [soll − grace, soll + grace] BEFORE all §4/§3
    # checks so compliance is assessed on credited time.
    from app.services import work_window_service
    _grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    _eff_start, _eff_end, _raw_start, _raw_end = work_window_service.clamp(
        current_user, entry.date, entry.start_time, entry.end_time, _grace,
    )
    # Fix #2: only overwrite start/end + raw_* when the respective time was
    # actually part of this partial update — mirrors the admin path
    # (admin_time_entries.py). A note-only edit must NOT re-clamp the stored
    # (already-credited) times and must NOT wipe raw_start/raw_end (§16 evidence;
    # §5 rest-time also reads the raw stamp). Without this gate a reine
    # Notiz-Änderung set raw_*=None and could lower Ist on a shifted soll window.
    if "start_time" in update_data:
        entry.start_time = _eff_start
        entry.raw_start_time = _raw_start
    if "end_time" in update_data:
        entry.end_time = _eff_end
        entry.raw_end_time = _raw_end

    exempt = current_user.exempt_from_arbzg

    # §3 ArbZG: daily hours hard cap – skipped for exempt users.
    # MUST run BEFORE the §4 break-waiver / approval branch below: a >10h day is
    # an absolute legal ceiling that no break waiver (and no approval workflow)
    # can lift. Computing + raising here ensures the edit is rejected regardless
    # of whether the practice requires approval for break exceptions (#144 fix).
    if not exempt and entry.end_time is not None:
        daily_hours = _calculate_daily_net_hours(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=entry.id,
            tenant_id=entry.tenant_id,
        )
        if daily_hours > MAX_DAILY_HOURS_HARD:
            raise HTTPException(
                status_code=422,
                detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG)."
            )

    # #144 §4 ArbZG: documented break-exception (only non-exempt users).
    waiver_reason = (entry_data.break_waiver_reason or "").strip()
    break_waiver_active = False

    # Break validation (ArbZG §4) – skipped for exempt users
    if not exempt and entry.end_time is not None:
        break_error = validate_daily_break(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=entry.id,
        )
        if break_error:
            if not waiver_reason:
                raise HTTPException(status_code=400, detail=break_error)

            if _break_exception_requires_approval(db, current_user.tenant_id):
                # Do not persist the edit — file an UPDATE ChangeRequest with the
                # employee's RAW (un-clamped) proposed times (§16, see snapshot
                # above) and revert the in-memory mutation. Clamping is applied
                # once, at approval, so raw_start/raw_end are preserved.
                cr = ChangeRequest(
                    user_id=entry.user_id,
                    tenant_id=current_user.tenant_id,
                    request_type=ChangeRequestType.UPDATE,
                    entry_kind="time_entry",
                    status=ChangeRequestStatus.PENDING,
                    time_entry_id=entry.id,
                    proposed_date=entry.date,
                    proposed_start_time=_intended_start,
                    proposed_end_time=_intended_end,
                    proposed_break_minutes=entry.break_minutes,
                    proposed_note=entry.note,
                    original_date=orig_snapshot["date"],
                    original_start_time=orig_snapshot["start_time"],
                    original_end_time=orig_snapshot["end_time"],
                    original_break_minutes=orig_snapshot["break_minutes"],
                    original_note=orig_snapshot["note"],
                    reason=waiver_reason,
                    break_waiver_reason=waiver_reason,
                )
                db.rollback()  # discard the in-memory edit on `entry`
                db.add(cr)
                db.commit()
                db.refresh(cr)
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "status": "pending_approval",
                        "change_request_id": str(cr.id),
                        "detail": (
                            "Pflicht-Pause-Ausnahme zur Genehmigung eingereicht. "
                            "Die Änderung wird nach Admin-Freigabe wirksam."
                        ),
                        "warnings": [f"BREAK_WAIVER_PENDING: {break_error}"],
                    },
                )

            break_waiver_active = True
            entry.break_waiver_reason = waiver_reason

    # #144 §4 ArbZG: audit trail for a documented break waiver on update.
    if break_waiver_active:
        _create_audit_log(
            db,
            entry.id,
            entry.user_id,
            current_user.id,
            action="update",
            old_entry=orig_snapshot,
            new_entry=entry,
            source=BREAK_WAIVER_SOURCE,
            tenant_id=current_user.tenant_id,
        )

    db.commit()
    db.refresh(entry)

    update_warnings: list[str] = []
    if break_waiver_active:
        waiver_detail = validate_daily_break(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=entry.id,
        )
        update_warnings.append(f"BREAK_WAIVER: {waiver_detail}")
    saved_hours = 0.0  # defined here so the night-worker check below can always reference it
    if not exempt and entry.end_time is not None:
        # #252: Diese Warn-Berechnung läuft NACH db.commit() — der bearbeitete
        # Eintrag steckt also schon (mit dem NEUEN Wert) in der DB. _calculate_*_
        # net_hours addiert die übergebenen Zeiten ZUSÄTZLICH zur Tabellen-Summe,
        # daher MUSS der Eintrag per exclude_entry_id ausgeschlossen werden, sonst
        # wird er doppelt gezählt (6h-Eintrag -> 12h -> fälschliche >8h-Warnung).
        saved_hours = _calculate_daily_net_hours(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=entry.id,
            tenant_id=entry.tenant_id,
        )
        if saved_hours > MAX_DAILY_HOURS_WARN:
            update_warnings.append("DAILY_HOURS_WARNING")
        weekly = _calculate_weekly_net_hours(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=entry.id,
            tenant_id=entry.tenant_id,
        )
        if weekly > MAX_WEEKLY_HOURS_WARN:
            update_warnings.append("WEEKLY_HOURS_WARNING")

    if not exempt:
        entry_weekday = entry.date.weekday()
        if entry_weekday == 6:
            update_warnings.append("SUNDAY_WORK")
        entry_is_holiday = is_holiday(db, entry.date, tenant_id=current_user.tenant_id)
        if entry_is_holiday:
            update_warnings.append("HOLIDAY_WORK")
        if (
            entry.end_time is not None
            and current_user.is_night_worker
            and is_night_work(entry.start_time, entry.end_time)
            and saved_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            update_warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({saved_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    # #377 § 2 Abs. 2 MiLoG: auch beim Bearbeiten (verändert die Monatssumme).
    # Nur bei Selbst-Bearbeitung — die Warnung gilt dem Eintrags-Eigentümer, nicht
    # einem (evtl. selbst geflaggten) fremd-bearbeitenden Akteur.
    if entry.user_id == current_user.id and current_user.milog_working_time_account:
        _m = milog_service.milog_50_check(
            db, current_user, entry.date.year, entry.date.month, up_to_date=entry.date)
        if _m:
            update_warnings.append(milog_service.milog_50_warning_text(_m))
        # #377 Baustein 2b: weiche Plausibilitäts-Warnung für Fix-Modus-MA.
        _mx = milog_service.monthly_exceeded_check(
            db, current_user, entry.date.year, entry.date.month, up_to_date=entry.date)
        if _mx:
            update_warnings.append(milog_service.monthly_exceeded_warning_text(_mx))

    response = TimeEntryResponse.model_validate(entry)
    _enrich_response(response, entry, current_user, db, warnings=update_warnings)
    return response


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a time entry."""
    entry = db.query(TimeEntry).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Check permissions
    if entry.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        # #120 (Review 2026-06-23): 404 statt 403 — ein fremder Same-Tenant-Eintrag
        # wird wie ein unbekannter behandelt (kein Existenz-Leak via Response-Code).
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")

    # Edit protection: employees can only delete today's entries
    if current_user.role != UserRole.ADMIN and entry.date != _today_local():
        raise HTTPException(
            status_code=403,
            detail="Einträge vergangener Tage können nur per Änderungsantrag gelöscht werden"
        )

    # §16 ArbZG / EuGH C-55/18: every deletion must leave an audit trail,
    # even when the user deletes their own same-day entry. The admin delete
    # path already logs — this mirrors that behaviour for employee self-delete.
    _create_audit_log(
        db,
        entry.id,
        entry.user_id,
        current_user.id,
        action="delete",
        old_entry=entry,
        source="manual",
        tenant_id=current_user.tenant_id,
    )

    db.delete(entry)
    db.commit()

    return None
