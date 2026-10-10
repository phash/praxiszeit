from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.services.date_filters import date_in_year, date_in_month
from typing import List, Optional
from datetime import datetime, date, time, timezone
from app.services.timezone_service import LOCAL_TZ, now_local as _now_local, today_local as _today_local
from app.database import get_db
from app.models import (
    User, TimeEntry, UserRole, TimeEntryAuditLog,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.services import settings_service, milog_service, calculation_service
from app.middleware.auth import get_current_user
from app.schemas.time_entry import (
    TimeEntryCreate, TimeEntryUpdate, TimeEntryResponse,
    ClockInRequest, ClockOutRequest, ClockStatusResponse,
)
from app.services.holiday_service import is_holiday
from app.services.break_validation_service import validate_daily_break, break_waiver_rejection
from app.services.arbzg_utils import is_night_work
from app.routers.admin_helpers import _create_audit_log, lock_user_row
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


def _net_hours(st: time, et: time, brk: int, uncredited: int) -> float:
    """Calculate net working hours from start/end time, break minutes and the
    uncredited minutes between work blocks (Spec 2026-10-08, E13).

    Invariant: et > st. This is NOT over-midnight aware on purpose — the system
    models over-midnight shifts as two separate entries, and end<=start is
    rejected on every write path (schema + router validation; the XLS importer
    skips such rows in execute_import). Reinterpreting et<st as "+1 day" would
    silently turn a data-entry error (e.g. swapped start/end) into a 16h shift,
    so we keep the max(0, …) floor as a last-resort guard instead.

    ``uncredited`` ist Pflicht: ohne ihn ergäbe „gestempelt 08:00–18:30,
    gekappt auf 18:15" bei einer Lücke von 2:30 h 10,25 h und HTTP 422, obwohl
    nur 7,75 h angerechnet sind (Spec 7.1).
    """
    mins = (et.hour * 60 + et.minute) - (st.hour * 60 + st.minute)
    return max(0.0, (mins - brk - uncredited) / 60.0)


def _calculate_daily_net_hours(
    db: Session,
    user_id: UUIDType,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    *,
    uncredited_minutes: int,
    exclude_entry_id=None,
    tenant_id=None,
) -> float:
    """Sum up all net hours for a user on a given date, including the new/updated entry.

    Bestehende Einträge tragen ihr gespeichertes ``uncredited_minutes`` bei;
    ``uncredited_minutes`` des neuen/geänderten Eintrags ist Pflicht (Spec 7.1),
    damit keine Aufrufstelle die Lücke still mitzählt.
    """
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

    total = sum(
        _net_hours(e.start_time, e.end_time, e.break_minutes, e.uncredited_minutes or 0)
        for e in existing
    )
    total += _net_hours(start_time, end_time, break_minutes, uncredited_minutes)
    return total


def _calculate_weekly_net_hours(
    db: Session,
    user_id: UUIDType,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    *,
    uncredited_minutes: int,
    exclude_entry_id=None,
    tenant_id=None,
) -> float:
    """Sum all net hours for the ISO calendar week containing entry_date, including the new/updated entry.

    ``uncredited_minutes`` wie im Tageshelfer (Pflicht; bestehende Einträge
    mit ihrem gespeicherten Wert).
    """
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

    total = sum(
        _net_hours(e.start_time, e.end_time, e.break_minutes, e.uncredited_minutes or 0)
        for e in existing
    )
    total += _net_hours(start_time, end_time, break_minutes, uncredited_minutes)
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


def _assert_within_employment_window(user: User, d: date) -> None:
    """400, wenn ``d`` vor ``first_work_day`` oder nach ``last_work_day`` der
    Person liegt. Eine Quelle für Einstempeln, Anlegen und den Datumswechsel
    beim Bearbeiten (#502) — gleicher Wortlaut an allen drei Stellen."""
    if user.first_work_day and d < user.first_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
    if user.last_work_day and d > user.last_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")


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
    """Close a stale open entry of a previous day.

    Spec E36/E42 (7.1 Nr. 13): läuft über ``clamp`` — das Ende 23:59 wird auf
    die Hülle (letzter Block + Puffer) gekappt, ``raw_end_time`` = 23:59, die
    Lückenminuten folgen dem Zeitpaar. Puffer = der gespeicherte des Eintrags
    aus ``clock_in`` (E80, ``grace_for_entry``). P18: ``auto_closed`` = True —
    23:59 ist dann ein synthetischer Wert, kein Stempel (nie anerkennen, nie als
    Anwesenheit oder „nicht angerechnet" zählen). Ohne Blöcke bleibt 23:59
    ungekappt (wie bisher), gekennzeichnet wird trotzdem.

    F-043: Does NOT commit — the caller's transaction owns the commit (und hält
    die Ankersperre, P5). Writes a TimeEntryAuditLog row with action=update /
    source=auto_close so stale auto-closes can be traced and so §3 ArbZG
    violations on previous days are not silently lost.
    """
    from app.services import work_window_service

    # Gekappt wird gegen die Person des Eintrags, nicht gegen den Aufrufer
    # (``changed_by_id`` kann künftig eine Admin sein, PR3/P23).
    owner = db.query(User).filter(
        User.id == entry.user_id,
        User.tenant_id == entry.tenant_id,  # F-026
    ).first()
    old_end_time = entry.end_time
    old_note = entry.note

    r = work_window_service.clamp(
        db, owner, entry.date, entry.start_time, work_window_service.AUTO_CLOSE_RAW_END,
        work_window_service.grace_for_entry(db, entry),
        credit_override=entry.credit_override,
    )
    entry.end_time = r.eff_end
    entry.raw_end_time = r.raw_end
    entry.uncredited_minutes = r.uncredited_minutes
    if r.grace_minutes is not None:
        entry.clamp_grace_minutes = r.grace_minutes
    entry.auto_closed = True
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

def _today_closed_net_minutes(db: Session, user: User, today: date) -> int:
    """#494: Σ net_hours der HEUTE abgeschlossenen Einträge, in Minuten.

    ``net_hours`` ist derselbe Wert, der ins Ist geht (gekappte Zeit #201, Pause
    abgezogen, nie negativ) — die Karte rechnet ihn bewusst nicht aus Start/Ende
    nach. ``net_hours`` ist auf 0,01 h gerundet (≤ 0,3 min Abweichung), daher
    ist das Runden auf ganze Minuten exakt.
    """
    closed = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026
        TimeEntry.date == today,
        TimeEntry.end_time.isnot(None),
    ).all()
    return int(round(sum(float(e.net_hours) for e in closed) * 60))


def _today_target_hours(db: Session, user: User, today: date) -> float:
    """#494/#431: Tagessoll von heute aus dem datumsaufgelösten Snapshot.

    Vorher las das Frontend ``user.hours_<wochentag>`` bzw. ``weekly_hours /
    work_days_per_week`` live von der User-Zeile — bei einer heute wirksamen
    Stundenänderung der falsche Wert.

    Review F1: über ``get_day_presence_target`` statt des reinen
    Wochentags-Vertragswerts — Feiertag, ganztägige Abwesenheit (jeden Typs),
    halber/freier 24./31.12. und das Beschäftigungsfenster ergeben 0 bzw. das
    anteilige Soll, sonst stand die Karte dort rot auf „0:00 von 8:00 h heute".
    """
    return float(calculation_service.get_day_presence_target(db, user, today))


@router.get("/clock-status", response_model=ClockStatusResponse)
def get_clock_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current clock-in/out status for the authenticated user.

    #494: zusätzlich ``today_net_minutes`` (Tages-Ist inkl. bereits
    abgeschlossener Blöcke) und ``today_target_hours`` (Tagessoll laut Snapshot).
    """
    today = _today_local()
    open_entry = _get_open_entry(db, current_user.id, tenant_id=current_user.tenant_id)

    # If the open entry is from a previous day, auto-close it.
    # P5: Ankersperre, danach den offenen Eintrag NEU lesen (ein paralleler
    # Schreiber kann ihn inzwischen geschlossen oder ersetzt haben).
    if open_entry is not None and open_entry.date != today:
        lock_user_row(db, current_user.tenant_id, current_user.id)
        # Ohne ``expire`` gäbe die zweite Abfrage dasselbe Objekt der
        # Identity-Map mit den VOR der Sperre gelesenen Werten zurück (Datum,
        # Notiz) — „neu lesen" hieße dann nur „Filter neu auswerten".
        db.expire(open_entry)
        open_entry = _get_open_entry(
            db, current_user.id, with_lock=True, tenant_id=current_user.tenant_id,
        )
        if open_entry is not None and open_entry.date != today:
            _close_stale_entry(db, open_entry, changed_by_id=current_user.id)
            db.commit()  # F-043: /clock-status owns the commit
            open_entry = None

    closed_minutes = _today_closed_net_minutes(db, current_user, today)
    target_hours = _today_target_hours(db, current_user, today)

    if not open_entry:
        return ClockStatusResponse(
            is_clocked_in=False,
            today_net_minutes=closed_minutes,
            today_target_hours=target_hours,
        )

    # Calculate elapsed minutes in local time
    now = _now_local()
    start_dt = datetime.combine(open_entry.date, open_entry.start_time, tzinfo=LOCAL_TZ)
    elapsed = int((now - start_dt).total_seconds() / 60)
    # Laufender Block netto: eine schon erfasste Pause abziehen; ein auf das
    # Arbeitszeitfenster gekappter Beginn kann nach „jetzt" liegen (#201) — das
    # darf das Tages-Ist nicht senken.
    running_net = max(0, elapsed - (open_entry.break_minutes or 0))

    response_entry = TimeEntryResponse.model_validate(open_entry)
    _enrich_response(response_entry, open_entry, current_user, db)

    return ClockStatusResponse(
        is_clocked_in=True,
        current_entry=response_entry,
        elapsed_minutes=elapsed,
        today_net_minutes=closed_minutes + running_net,
        today_target_hours=target_hours,
    )


@router.post("/clock-in", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def clock_in(
    body: ClockInRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clock in: create a time entry with start_time=now, end_time=NULL."""
    # VULN-009 / Review 2026-07-14: unter READ COMMITTED sperrt ein
    # `SELECT ... FOR UPDATE` auf NULL Treffer (die typische Lage vor dem
    # ERSTEN Einstempeln des Tages) gar nichts — man kann keine Phantomzeile
    # sperren. Zwei echt-gleichzeitige clock-in-Requests sehen dann BEIDE
    # "kein offener Eintrag" und legen beide eine neue Zeile an; bisher wurde
    # das nur zufällig durch `uq_tenant_user_date_start` aufgefangen (weil
    # start_time auf die Minute gerundet wird), nicht durch den Lock unten.
    # Serialize concurrent clock-ins for THIS user: die Anker-Sperre auf der
    # (existierenden) User-Zeile greift wirklich (anders als ein FOR UPDATE auf
    # dem noch nicht existierenden offenen TimeEntry), so a truly-concurrent
    # second clock-in blocks here, then sees the first's committed open entry via
    # _get_open_entry and returns the "already clocked in" path instead of
    # inserting a duplicate. (Same pattern as absences.py's User-row anchor lock.)
    # Audit 2026-07-31 (Restklasse): ueber den gemeinsamen Helfer, also
    # ``FOR NO KEY UPDATE`` — clock_in schreibt danach TimeEntry- und
    # Audit-Zeilen mit Fremdschluesseln auf ``users``. Zwei Anker schliessen
    # sich weiterhin gegenseitig aus, die Serialisierung bleibt also erhalten;
    # Begruendung im Kopf von ``admin_helpers``.
    lock_user_row(db, current_user.tenant_id, current_user.id)

    # `_get_open_entry(with_lock=True)` bleibt als defense-in-depth: sobald die
    # Zeile existiert (Stale-Entry von gestern, s.u.), sperrt FOR UPDATE hier
    # echt und verhindert eine parallele Änderung/Auto-Close-Race auf genau
    # dieser Zeile. Gegen den Kaltstart-Wettlauf genügt bei clock_out
    # (existierende offene Zeile) diese Zeilensperre; den Anker nimmt clock_out
    # trotzdem zuerst, wegen P5 (Spec 2026-10-08: Snapshot-Konsistenz gegenüber
    # laufenden Arbeitszeit-Änderungen) — nicht zurückbauen.
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
    _assert_within_employment_window(current_user, now.date())

    # #201: clamp early start to [soll_start − grace]; preserve raw stamp.
    from app.services import work_window_service
    grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    start_t = now.time().replace(second=0, microsecond=0)
    _r = work_window_service.clamp(
        db, current_user, now.date(), start_t, None, grace, credit_override=False,
    )
    eff_start, raw_start = _r.eff_start, _r.raw_start

    entry = TimeEntry(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        date=now.date(),
        start_time=eff_start,
        raw_start_time=raw_start,
        # Spec 7.1 Nr. 1: offen → 0, Lücken zählen erst mit dem Ende.
        uncredited_minutes=_r.uncredited_minutes,
        # Spec E79/E80: Neuanlage merkt sich den aktuellen Puffer; clock_out
        # kappt das Ende später mit genau diesem Wert (None = keine Blöcke).
        clamp_grace_minutes=_r.grace_minutes,
        end_time=None,
        break_minutes=0,
        note=body.note,
    )

    # §5 ArbZG: Ruhezeit-Warnung (11h seit letztem Arbeitsende)
    clock_in_warnings: list[str] = []
    # #462: Vor der Hülle meldet EARLY_START die Kappung (zielgruppengerecht,
    # keine zweite WORK_WINDOW_CLAMPED-Meldung — zwei Warnungen fuer eine
    # Kappung waeren Laerm). Spec 6.2/7.1 Nr. 1: wer ZWISCHEN zwei Bloecken
    # einstempelt, bekommt den gemeinsamen Lueckentext („angerechnet wird erst
    # ab …").
    if raw_start is not None:
        clock_in_warnings.append(
            f"EARLY_START: Du hast vor deinem Soll-Beginn eingestempelt — angerechnet ab {eff_start.strftime('%H:%M')}."
        )
    else:
        # Spec 6.2: Einstempeln zwischen zwei Bloecken (K2) — derselbe Text wie
        # ueberall, angerechnet wird erst ab dem Ende der Luecke.
        _gap_warn = work_window_service.clamp_warning(
            db, current_user, now.date(), _r, for_employee=True,
        )
        if _gap_warn:
            clock_in_warnings.append(_gap_warn)
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
    # P5 (Spec 2.10): Ankersperre als ERSTE Datenbankaktion — vor Puffer,
    # Snapshot und clamp, vor der Zeilensperre auf den offenen Eintrag. Sonst
    # kappt ein Ausstempeln während einer laufenden Arbeitszeit-Änderung noch
    # gegen den alten Snapshot und entgeht deren Neuberechnung.
    lock_user_row(db, current_user.tenant_id, current_user.id)
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
    # E80: Einzel-Neukappung des offenen Eintrags mit SEINEM Puffer aus clock_in.
    grace = work_window_service.grace_for_entry(db, open_entry)
    _r = work_window_service.clamp(
        db, current_user, open_entry.date, open_entry.start_time, new_end_time, grace,
        credit_override=open_entry.credit_override,
    )
    eff_end, raw_end = _r.eff_end, _r.raw_end
    # Spec 8.2: Lückensegmente aus DENSELBEN Eingaben wie ``clamp`` für §4.
    _segs = work_window_service.gap_segments(
        db, current_user, open_entry.date, open_entry.start_time, new_end_time, grace,
        credit_override=open_entry.credit_override,
    )

    # §3 ArbZG: check daily hours before committing – skipped for exempt users
    daily_hours = _calculate_daily_net_hours(
        db=db,
        user_id=current_user.id,
        entry_date=open_entry.date,
        start_time=open_entry.start_time,
        end_time=eff_end,
        break_minutes=body.break_minutes,
        uncredited_minutes=_r.uncredited_minutes,
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

    # #499 (Kundenmeldung): §4 ArbZG wird über den ganzen TAG geprüft — und
    # anders als §3 BLOCKIERT ein Verstoß das Ausstempeln jetzt (400), solange
    # weder ausreichende Pause noch eine zulässige Begründung mitkommt. Bis
    # 1.19.x war das nur eine weiche Warnung; zusammen mit dem Ausstempel-Dialog,
    # der allein den laufenden Block ansah, ließen sich so zwei aneinander-
    # gereihte Einträge (08:49–13:59 + 13:59–18:00) ohne Pause und ohne
    # Begründung schließen. Anders als bei §3 kann die Person den Verstoß im
    # selben Aufruf beheben (Pause eintragen oder — falls erlaubt — begründen),
    # sie bleibt also nicht dauerhaft eingestempelt. Geprüft wird VOR dem
    # Schreiben: der get_db-Rollback lässt den Eintrag dann unverändert offen.
    waiver_reason = (body.break_waiver_reason or "").strip()
    break_error = None
    if not exempt:
        break_error = validate_daily_break(
            db=db,
            user=current_user,
            entry_date=open_entry.date,
            start_time=open_entry.start_time,
            end_time=eff_end,
            break_minutes=body.break_minutes,
            uncredited_segments=_segs,
            exclude_entry_id=open_entry.id,
            tenant_id=current_user.tenant_id,
        )
        if break_error:
            rejection = break_waiver_rejection(
                db, current_user.tenant_id, break_error, waiver_reason,
            )
            if rejection:
                raise HTTPException(status_code=400, detail=rejection)

    open_entry.end_time = eff_end
    open_entry.raw_end_time = raw_end
    open_entry.auto_closed = False  # P18: echtes Ende gestempelt
    # Spec 7.1 Nr. 2 (E11): die Lückenminuten folgen dem geschriebenen Ende.
    open_entry.uncredited_minutes = _r.uncredited_minutes
    if _r.grace_minutes is not None:
        open_entry.clamp_grace_minutes = _r.grace_minutes
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
    # #462: dasselbe beim Ausstempeln — hier wird das ENDE gekappt. Gemeldet wird
    # nur, was tatsächlich gespeichert ist: clock_out schreibt allein das Ende, der
    # Beginn bleibt, wie clock_in ihn gespeichert hat. Haben sich Blöcke oder
    # Puffer seit dem Einstempeln geändert, kappt clamp den gespeicherten Beginn
    # rechnerisch erneut — eine daraus gemeldete Beginn-Kappung widerspräche dem
    # gespeicherten Eintrag (#462-Klasse, Review Task 3). Der Kollaps-Text bleibt
    # gleich (dort ist eff_start == start), der Lückenanteil ebenso (Lücken liegen
    # hinter der Hüllkante).
    _clamp_warn = work_window_service.clamp_warning(
        db, current_user, open_entry.date,
        _r._replace(eff_start=open_entry.start_time, raw_start=None), for_employee=True,
    )
    if _clamp_warn:
        clock_out_warnings.append(_clamp_warn)
    if break_error:
        # M-ARB1: die zulässige Begründung (oben durch break_waiver_rejection
        # freigegeben) dokumentiert die §4-Abweichung am Eintrag + im
        # Änderungsprotokoll (source='break_waiver'), wie bei Anlage/Antrag (#144).
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
            uncredited_minutes=_r.uncredited_minutes,
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
    # P5 (Spec 2.10): Ankersperre als ERSTE Datenbankaktion — vor Puffer,
    # Snapshot und clamp. Sonst kappt eine Neuanlage während einer laufenden
    # Arbeitszeit-Änderung noch gegen den alten Snapshot und entgeht deren
    # Neuberechnung.
    lock_user_row(db, current_user.tenant_id, current_user.id)

    # Edit protection: employees can only create entries for today
    if current_user.role != UserRole.ADMIN and entry_data.date != _today_local():
        raise HTTPException(
            status_code=403,
            detail="Einträge für vergangene Tage können nur per Änderungsantrag erstellt werden"
        )

    # Check first/last work day
    _assert_within_employment_window(current_user, entry_data.date)

    exempt = current_user.exempt_from_arbzg

    # #201: clamp start/end to [soll − grace, soll + grace] BEFORE all §4/§3
    # checks so that compliance is assessed on the credited (angerechnete) time,
    # not on the raw input. raw_* store the original stamp when clamping occurs.
    from app.services import work_window_service
    _grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    _r = work_window_service.clamp(
        db, current_user, entry_data.date, entry_data.start_time, entry_data.end_time, _grace,
        credit_override=False,
    )
    eff_start, eff_end, raw_start, raw_end = _r.eff_start, _r.eff_end, _r.raw_start, _r.raw_end
    # Spec 8.2: Lückensegmente aus DENSELBEN Eingaben wie ``clamp`` für §4.
    _segs = work_window_service.gap_segments(
        db, current_user, entry_data.date, entry_data.start_time, entry_data.end_time, _grace,
        credit_override=False,
    )

    # Duplikatsprüfung NACH dem Kappen (Release-Review 1.16.0). Gespeichert wird
    # `eff_start`, geprüft wurde vorher die ROHE `entry_data.start_time` — zwei
    # verschiedene Rohzeiten innerhalb des Puffers werden aber auf dieselbe
    # Startzeit gekappt. Die Sonde lief dann ins Leere und erst der UNIQUE-Index
    # `uq_tenant_user_date_start` schlug zu: HTTP 500 statt des gemeinten 409.
    # `admin_time_entries` prüft bereits gegen die gekappte Zeit.
    existing = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
        TimeEntry.date == entry_data.date,
        TimeEntry.start_time == eff_start,
    ).first()

    if existing:
        # B-L4: duplicate entry is a conflict, not a bad request — align with
        # the 409 used by the CR-approval and absence duplicate paths.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es existiert bereits ein Eintrag mit dieser Startzeit an diesem Datum"
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
        uncredited_minutes=_r.uncredited_minutes,
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
            user=current_user,
            entry_date=entry_data.date,
            start_time=eff_start,
            end_time=eff_end,
            break_minutes=entry_data.break_minutes,
            uncredited_segments=_segs,
            tenant_id=current_user.tenant_id,
        )
        if break_error:
            # No (permitted) documented exception → the §4 block stands.
            # #499: the tenant may switch the exception off altogether — then
            # even a supplied reason is rejected (and no approval CR is filed).
            rejection = break_waiver_rejection(
                db, current_user.tenant_id, break_error, waiver_reason,
            )
            if rejection:
                raise HTTPException(status_code=400, detail=rejection)

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
                    # Release-Review 1.19.3 (F3): §10-Grund mitnehmen (#485).
                    proposed_sunday_exception_reason=entry_data.sunday_exception_reason,
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
    # #462: Kappung melden (manuelles Anlegen durch die MA selbst).
    _clamp_warn = work_window_service.clamp_warning(
        db, current_user, entry_data.date, _r, for_employee=True,
    )
    if _clamp_warn:
        warnings.append(_clamp_warn)
    if break_waiver_active:
        # Re-run validation to surface the concrete §4 detail in the warning.
        waiver_detail = validate_daily_break(
            db=db,
            user=current_user,
            entry_date=entry_data.date,
            start_time=eff_start,
            end_time=eff_end,
            break_minutes=entry_data.break_minutes,
            uncredited_segments=_segs,
            tenant_id=current_user.tenant_id,
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
            uncredited_minutes=_r.uncredited_minutes,
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
        # Spec 7.1 Nr. 3 (E11): Lückenminuten immer serverseitig aus clamp().
        uncredited_minutes=_r.uncredited_minutes,
        # Spec E79/E80: Neuanlage merkt sich den aktuellen Puffer.
        clamp_grace_minutes=_r.grace_minutes,
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
    # P5: Ankersperre auf den EIGENTÜMER vor jeder Zeilensperre. Der Eigentümer
    # eines Eintrags ist unveränderlich — ein ungesperrter Lesezugriff genügt.
    _owner_id = db.query(TimeEntry.user_id).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
    ).scalar()
    if _owner_id is not None:
        lock_user_row(db, current_user.tenant_id, _owner_id)
    entry = db.query(TimeEntry).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
    ).with_for_update().first()

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
    # #502: die Sperre oben prüft nur das GESPEICHERTE Datum. Ohne diese zweite
    # Hälfte verschob ein ``{"date": "<vergangener Sonntag>"}`` den heutigen,
    # noch offenen Eintrag in die Vergangenheit — ohne Ende liefen §3/§4 nicht,
    # und der Auto-Close schloss ihn danach um 23:59 (bis rund 16 h an einem
    # vergangenen Tag, ohne Antrag). Für Mitarbeitende bleibt nur heute → heute
    # (das Formular schickt das Datum immer mit). Vor dem Übernehmen der Felder.
    if (current_user.role != UserRole.ADMIN
            and "date" in entry_data.model_fields_set
            and entry_data.date != _today_local()):
        raise HTTPException(
            status_code=403,
            detail="Einträge vergangener Tage können nur per Änderungsantrag geändert werden"
        )

    # P3: ein anerkannter Eintrag wird nicht still per MA-PUT neu gekappt —
    # die Änderung läuft über einen Antrag (die Verwaltung bestätigt dort).
    # Admins auf dieser Route SIND die Verwaltung: Flag bleibt, keine Kappung.
    if entry.credit_override and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=409,
            detail="Anerkannter Eintrag – Änderung bitte per Änderungsantrag.",
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
        # P18: ob 23:59 im Rohende ein synthetischer Wert des Auto-Close ist.
        "auto_closed": entry.auto_closed,
        # P28: Vorher-Stand der nicht angerechneten Lückenminuten für den
        # Snapshot eines Waiver-Antrags.
        "uncredited_minutes": entry.uncredited_minutes,
    }

    # Release-Review 1.16.0: gegen den EIGENTÜMER des Eintrags kappen und prüfen,
    # nicht gegen den Aufrufer. Diese Route lässt Admins fremde Einträge bearbeiten
    # (Ownership-Check weiter oben) — mit `current_user` las der Code dann das
    # Arbeitszeitfenster, `exempt_from_arbzg` und `is_night_worker` des ADMINS.
    # Ein §18-befreiter Praxisinhaber konnte so für eine nicht befreite MFA einen
    # 12-Stunden-Tag ohne Pause speichern, weil die §3-Hartgrenze übersprungen
    # wurde. `admin_time_entries.admin_update_time_entry` macht es bereits richtig.
    _entry_owner = (
        current_user if entry.user_id == current_user.id
        else db.query(User).filter(
            User.id == entry.user_id,
            User.tenant_id == current_user.tenant_id,  # F-026
        ).first()
    )
    # Spec 8.2: §4 rechnet mit den Einträgen der Person des Eintrags, §3 mit
    # ``entry.user_id`` — beides muss dieselbe Person sein. Kein Rückfall auf den
    # Aufrufer (falsch zugeordnete Zeile, F-026): dann prüfte §4 die Einträge der
    # bearbeitenden Admin. 404 wie in ``admin_update_time_entry``.
    if _entry_owner is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # #502: ein Datumswechsel landet nur im Beschäftigungsfenster der Person des
    # Eintrags — wie beim Anlegen (``create_time_entry``), auch für Admins. Nur
    # ein tatsächlicher WECHSEL: das Formular schickt das gespeicherte Datum
    # immer mit, und ein Alteintrag außerhalb eines später gesetzten Fensters
    # muss per Zeit-/Notizkorrektur reparierbar bleiben.
    if (entry_data.date is not None
            and "date" in entry_data.model_fields_set
            and entry_data.date != entry.date):
        _assert_within_employment_window(_entry_owner, entry_data.date)

    # Update fields
    update_data = entry_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    # Validate end_time > start_time (only if both are set)
    if entry.end_time is not None and entry.end_time <= entry.start_time:
        raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

    # Audit 2026-07-31 (U2): einen LAUFENDEN Eintrag (bisher ohne Ende) darf
    # dieser Pfad nicht mit einer noch nicht erreichten Uhrzeit schliessen. Das
    # Bearbeiten-Formular belegte „Bis" mit dem festen Wert 17:00 vor und schickte
    # es immer mit — wer mittags eine Notiz nachtrug, schloss damit unbemerkt
    # seinen laufenden Eintrag auf 17:00. Beim naechsten Einstempeln entstand eine
    # zweite, ueberlappende Zeile (eine Ueberschneidungspruefung gibt es nicht),
    # und §4 meldete eine verwirrende Pausenverletzung fuer nie gearbeitete Zeit.
    # Fuer §16 ist eine Endzeit in der Zukunft eine erfundene Zeit.
    #
    # Bewusst eng: der Anlege-Pfad laesst fuer HEUTE weiterhin eine spaetere
    # Uhrzeit zu (nur das Datum ist auf „nicht in der Zukunft" begrenzt, siehe
    # TimeEntryBase.validate_not_future). Eine Sperre auch fuer bereits
    # geschlossene Eintraege waere dazu asymmetrisch (loeschen + neu anlegen
    # umginge sie) und gehoert an beide Pfade gemeinsam — siehe Bericht.
    if (orig_snapshot["end_time"] is None
            and update_data.get("end_time") is not None
            and entry.date == _today_local()
            and update_data["end_time"] > _now_local().time()):
        raise HTTPException(
            status_code=400,
            detail=(
                "Das Ende darf nicht in der Zukunft liegen — der Eintrag läuft "
                "noch. Bitte die tatsächliche Endzeit eintragen oder ausstempeln."
            ),
        )

    # §16/#201: snapshot the employee's intended RAW times BEFORE the clamp below
    # overwrites entry.start/end with credited time. An approval-required waiver
    # CR (further down) must carry these raw values so the clamp at approval can
    # reconstruct raw_start/raw_end. If start/end were not part of this partial
    # update, fall back to the entry's existing raw stamp (or its start/end).
    _intended_start = (
        entry.start_time if "start_time" in update_data
        else (orig_snapshot["raw_start_time"] or orig_snapshot["start_time"])
    )
    # P18 (Review Task 8): beim automatisch geschlossenen Eintrag ist das
    # Rohende 23:59 kein Stempel — der Antrag trägt dann das wirksame Ende und
    # behauptet kein Ende, das niemand eingetragen hat. Die Genehmigung stellt
    # am selben Tag über ``end_input_for`` das Rohende 23:59 trotzdem wieder her
    # (bei einem Datumswechsel bleibt es beim wirksamen Ende, PR1-Review F1).
    _intended_end = (
        entry.end_time if "end_time" in update_data
        else orig_snapshot["end_time"] if orig_snapshot["auto_closed"]
        else (orig_snapshot["raw_end_time"] or orig_snapshot["end_time"])
    )

    # #201: clamp start/end to [soll − grace, soll + grace] BEFORE all §4/§3
    # checks so compliance is assessed on credited time.
    from app.services import work_window_service
    # E80: Einzel-Neukappung eines gespeicherten Eintrags mit SEINEM Puffer
    # (NULL → aktueller Mandanten-Puffer); eine spätere Puffer-Senkung kürzt
    # die angerechnete Zeit damit nicht nebenbei.
    _grace = work_window_service.grace_for_entry(db, entry)
    # Release-Review 1.19.1: wie im Admin-Pfad — kommt die bereits gekappte Zeit
    # unveraendert zurueck, mit dem Rohwert weiterrechnen, statt raw_* zu loeschen.
    # ``entry.start_time`` traegt hier bereits den Wert aus ``update_data``; der
    # zuvor gespeicherte Stand steckt in ``orig_snapshot``. Fuer ein Feld, das gar
    # nicht Teil des Updates war, liefert die Ruecksetzung den Rohwert und die
    # Kappung daraus wieder exakt dieselbe angerechnete Zeit — §3/§4 pruefen also
    # unveraendert gegen die angerechnete Zeit.
    _clamp_start = work_window_service.unclamp_input(
        entry.start_time, orig_snapshot["start_time"], orig_snapshot["raw_start_time"],
    )
    # PR1-Review F1 (P18): wird ein automatisch geschlossener Eintrag (nur Admins, MA
    # verschieben nicht, #502) auf einen anderen Tag gelegt, gilt das wirksame
    # Ende statt des Rohendes 23:59.
    _clamp_end = work_window_service.end_input_for(
        entry.end_time, orig_snapshot["end_time"], orig_snapshot["raw_end_time"],
        auto_closed=orig_snapshot["auto_closed"], prev_date=orig_snapshot["date"],
        target_date=entry.date,
    )
    # Die Prüfung oben sah die rohe Eingabe; ``end_input_for`` kann das Ende davor
    # legen (verschobener Auto-Close-Eintrag, späterer Beginn) — gespeichert würde
    # end < start mit net 0, ohne Warnung.
    _order_error = work_window_service.input_order_error(
        _clamp_start, _clamp_end, auto_closed=orig_snapshot["auto_closed"],
    )
    if _order_error:
        raise HTTPException(status_code=400, detail=_order_error)
    _r = work_window_service.clamp(
        db, _entry_owner, entry.date, _clamp_start, _clamp_end, _grace,
        credit_override=entry.credit_override,
    )
    _eff_start, _eff_end, _raw_start, _raw_end = _r.eff_start, _r.eff_end, _r.raw_start, _r.raw_end
    # Spec 8.2: Lückensegmente aus DENSELBEN Eingaben wie ``clamp`` für §4.
    _segs = work_window_service.gap_segments(
        db, _entry_owner, entry.date, _clamp_start, _clamp_end, _grace,
        credit_override=entry.credit_override,
    )
    # Fix #2: only overwrite start/end + raw_* when the respective time was
    # actually part of this partial update — mirrors the admin path
    # (admin_time_entries.py). A note-only edit must NOT re-clamp the stored
    # (already-credited) times and must NOT wipe raw_start/raw_end (§16 evidence;
    # §5 rest-time also reads the raw stamp). Without this gate a reine
    # Notiz-Änderung set raw_*=None and could lower Ist on a shifted soll window.
    # E39 (Spec 2026-10-08): ein reiner Datumswechsel auf einen anderen
    # Wochentag kappt neu — das gespeicherte Paar gehört zum alten Tag. Die
    # Rücksetzung oben liefert dafür den Rohstempel, die Kappung rechnet ihn
    # gegen die Blöcke des NEUEN Datums.
    _times_written = any(k in update_data for k in ("start_time", "end_time", "date"))
    if "start_time" in update_data or "date" in update_data:
        entry.start_time = _eff_start
        entry.raw_start_time = _raw_start
    if "end_time" in update_data or "date" in update_data:
        entry.end_time = _eff_end
        entry.raw_end_time = _raw_end
    if _times_written:
        # Spec E11/E79: Lückenminuten und angewandter Puffer folgen dem
        # geschriebenen Zeitpaar. Ohne Zeit- oder Datumsfeld im Update bleibt der
        # gespeicherte Wert stehen (passend zu den unverändert gespeicherten
        # Zeiten, Fix #2); ein None-Puffer (Tag ohne Blöcke) lässt den
        # gespeicherten Wert stehen.
        entry.uncredited_minutes = _r.uncredited_minutes
        if _r.grace_minutes is not None:
            entry.clamp_grace_minutes = _r.grace_minutes
    # P18: nur ein ANDERES Ende als das gespeicherte wirksame ist eine echte
    # Korrektur; das Formular schickt das wirksame Ende sonst unverändert mit
    # (``end_input_for`` rechnet am selben Tag dann mit dem synthetischen 23:59
    # weiter, das Kennzeichen bleibt). Ebenso wenig das zurückgeschickte Rohende 23:59
    # eines automatisch geschlossenen Eintrags (Review Task 8). Nie über die
    # generische ``setattr``-Schleife oben — ``auto_closed`` ist kein
    # Schemafeld (E11).
    if "end_time" in update_data and work_window_service.end_is_correction(
        update_data["end_time"], orig_snapshot["end_time"],
        orig_snapshot["raw_end_time"], orig_snapshot["auto_closed"],
    ):
        entry.auto_closed = False

    exempt = _entry_owner.exempt_from_arbzg

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
            uncredited_minutes=entry.uncredited_minutes,
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
            user=_entry_owner,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            uncredited_segments=_segs,
            exclude_entry_id=entry.id,
            tenant_id=entry.tenant_id,
        )
        if break_error:
            # #499: einheitliche Entscheidung (Begründung fehlt / Ausnahme
            # im Mandanten abgeschaltet → 400).
            rejection = break_waiver_rejection(
                db, current_user.tenant_id, break_error, waiver_reason,
            )
            if rejection:
                raise HTTPException(status_code=400, detail=rejection)

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
                    original_uncredited_minutes=orig_snapshot["uncredited_minutes"],  # P28
                    reason=waiver_reason,
                    break_waiver_reason=waiver_reason,
                    # Release-Review 1.19.3 (F3): §10-Grund vor dem Rollback sichern
                    # (neuer Wert, falls mitgeschickt, sonst der bestehende — die
                    # Genehmigung schreibt beides korrekt zurueck).
                    proposed_sunday_exception_reason=entry.sunday_exception_reason,
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
    # #462: nur wenn die gekappte Zeit auch geschrieben wird — eine reine
    # Notiz-Aenderung fasst start/end nicht an (Fix #2) und darf nichts melden.
    # Release-Review 1.19.1: zusaetzlich muss sich die eingereichte Zeit von der
    # gespeicherten unterscheiden — das Formular schickt die angerechnete Zeit
    # immer mit, und eine erneute Meldung derselben alten Kappung ist Laerm.
    # E39: ein Datumswechsel ist nie „unveraendert" — dieselbe Rohzeit an einem
    # anderen Wochentag kappt anders und muss gemeldet werden (#462-Klasse).
    _resubmitted_unchanged = (
        entry.date == orig_snapshot["date"]
        and _clamp_start == (orig_snapshot["raw_start_time"] or orig_snapshot["start_time"])
        and _clamp_end == (orig_snapshot["raw_end_time"] or orig_snapshot["end_time"])
    )
    if _times_written and not _resubmitted_unchanged:
        # Spec 6.2: der Hinweis „Anrechnung beantragen" gilt der Person des
        # Eintrags. Eine Admin, die hier einen fremden Eintrag bearbeitet, ist
        # die Verwaltung (P3, siehe oben) und erkennt selbst an — wie bei der
        # MiLoG-Warnung weiter unten entscheidet die Selbst-Bearbeitung.
        _clamp_warn = work_window_service.clamp_warning(
            db, _entry_owner, entry.date, _r,
            for_employee=(entry.user_id == current_user.id),
        )
        if _clamp_warn:
            update_warnings.append(_clamp_warn)
    if break_waiver_active:
        waiver_detail = validate_daily_break(
            db=db,
            user=_entry_owner,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            uncredited_segments=_segs,
            exclude_entry_id=entry.id,
            tenant_id=entry.tenant_id,
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
            uncredited_minutes=entry.uncredited_minutes,
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
            uncredited_minutes=entry.uncredited_minutes,
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
            and _entry_owner.is_night_worker
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
