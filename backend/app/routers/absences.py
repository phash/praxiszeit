from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.services.date_filters import date_in_year, date_in_month, parse_year_month
from sqlalchemy import extract
from typing import List, Optional
from datetime import timedelta, date
from app.services.timezone_service import today_local
from app.database import get_db
from app.models import (
    User, Absence, AbsenceType, UserRole, PublicHoliday, TimeEntry, TimeEntryAuditLog,
    AbsenceReason, AbsenceReasonBehavior, BEHAVIOR_TO_ABSENCE_TYPE,
)
from app.middleware.auth import get_current_user
from app.schemas.absence import AbsenceCreate, AbsenceResponse, AbsenceCalendarEntry, TeamAbsenceEntry, NextVacationResponse
from app.services import calculation_service, settings_service
from app.routers.admin_helpers import _create_audit_log

router = APIRouter(prefix="/api/absences", tags=["absences"])

# DSGVO Art. 9: in the colleague-facing feeds (team calendar / upcoming), the
# masked bucket must NOT be a 1:1 tell for sick-leave. If only SICK were
# rewritten to "absent" while every other type kept its real value, the unique
# "absent" bucket would let any non-admin deterministically infer a coworker's
# health status. We therefore collapse the sensitive / unspecified types into
# the same generic "absent" bucket; non-sensitive planning types (VACATION,
# TRAINING, OVERTIME) stay truthful so colleagues can still coordinate cover.
_MASKED_ABSENCE_TYPES = {AbsenceType.SICK, AbsenceType.OTHER, AbsenceType.PAID_LEAVE}


@router.get("/daily-target")
def get_daily_target_for_date_endpoint(
    target_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get daily target hours for a specific date (for pre-filling absence forms)."""
    weekly = calculation_service.get_weekly_hours_for_date(db, current_user, target_date)
    daily = calculation_service.get_daily_target_for_date(current_user, target_date, weekly_hours=weekly)
    return {"date": str(target_date), "hours": float(daily)}


@router.get("/", response_model=List[AbsenceResponse])
def list_absences(
    year: Optional[int] = Query(None, description="Filter by year"),
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List absences.
    Regular users can only see their own absences.
    Admins can filter by user_id.
    """
    # F-026 belt-and-suspenders: explicit tenant scope on top of RLS — the admin
    # branch below accepts an arbitrary user_id from the caller.
    query = db.query(Absence).filter(Absence.tenant_id == current_user.tenant_id)

    # If user_id is provided, only admin can filter by it
    if user_id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
        query = query.filter(Absence.user_id == user_id)
    else:
        # Regular users only see their own absences
        query = query.filter(Absence.user_id == current_user.id)

    # Filter by year if provided
    if year:
        query = query.filter(date_in_year(Absence.date, year))

    absences = query.order_by(Absence.date.desc()).offset(skip).limit(limit).all()

    # DSGVO Art. 9/32 (Audit M): Admin-Zugriff auf FREMDE Gesundheitsdaten
    # (Krank/Sonstiges/bezahlte Freistellung) protokollieren — eine Zeile pro
    # Request (nicht pro Eintrag), nur beim gezielten Einzel-MA-Adminblick.
    if (
        current_user.role == UserRole.ADMIN
        and user_id
        and str(user_id) != str(current_user.id)
    ):
        # #208 / Art. 9 + Art. 5(2): JEDEN gezielten Admin-Lesezugriff auf fremde
        # Abwesenheiten protokollieren (eine Zeile pro Request) — nicht nur, wenn
        # Gesundheitsdaten IM ERGEBNIS landen. Sonst haengt die Spur am Inhalt:
        # eine gezielte Suche nach Krankmeldungen, die (noch) nichts findet,
        # bliebe unprotokolliert.
        # #312: a custom-reason absence may be health-sensitive (e.g. "Reha"
        # mapped to TRAINING), so it counts as sensitive for the audit trail too
        # — consistent with the colleague-feed masking.
        sensitive = any(
            a.type in _MASKED_ABSENCE_TYPES or a.reason_id is not None
            for a in absences
        )
        db.add(TimeEntryAuditLog(
            time_entry_id=None,
            user_id=user_id,
            changed_by=current_user.id,
            action="health_data_read" if sensitive else "absence_list_read",
            new_note=("Admin-Lesezugriff auf fremde Abwesenheiten "
                      + ("inkl. Gesundheitsdaten" if sensitive else "ohne Gesundheitsdaten")),
            source="dsgvo",
            tenant_id=current_user.tenant_id,
        ))
        db.commit()

    return absences


@router.get("/calendar", response_model=List[AbsenceCalendarEntry])
def get_absence_calendar(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get absence calendar for all employees for a specific month.
    Visible to all authenticated users.
    """
    try:
        year, month_num = parse_year_month(month)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    # Get all absences for the month, fetching User columns in the same query
    rows = db.query(
        Absence, User.first_name, User.last_name, User.calendar_color, User.department
    ).join(User).filter(
        # F-026: this standalone calendar query broadcasts absences tenant-wide
        # — pin it to the caller's tenant explicitly, not just via RLS.
        Absence.tenant_id == current_user.tenant_id,
        User.is_active == True,
        User.is_hidden == False,
        date_in_month(Absence.date, year, month_num)
    ).order_by(Absence.date).all()

    # #312: custom-reason labels (batch-loaded once) — shown to admins/owners,
    # masked for colleagues (a custom reason may be health-sensitive, e.g. "Reha").
    # Key on str(id) so the lookup is robust to UUID-vs-string typing (SQLite).
    reason_names = {
        str(r.id): r.name for r in db.query(AbsenceReason.id, AbsenceReason.name)
        .filter(AbsenceReason.tenant_id == current_user.tenant_id).all()
    }

    # Convert to calendar entries (no extra queries needed)
    # DSGVO Art. 9: Krankheitsdaten sind besonders schützenswert.
    # Nicht-Admins sehen fremde Krankmeldungen nur als "absent".
    calendar_entries = []
    for absence, first_name, last_name, calendar_color, department in rows:
        display_type = absence.type.value
        # #312: any custom-reason absence is masked for non-admin colleagues too.
        masked = (
            (absence.type in _MASKED_ABSENCE_TYPES or absence.reason_id is not None)
            and current_user.role != UserRole.ADMIN
            and absence.user_id != current_user.id
        )
        if masked:
            display_type = "absent"
        elif absence.reason_id is not None:
            display_type = reason_names.get(str(absence.reason_id), display_type)
        # DSGVO-Minimierung: die Abteilung (Org-Zuordnung) wird nur Admins
        # ausgeliefert (Filter-Use-Case). Kolleg:innen erhalten den Team-Kalender
        # ohne Abteilungsmerkmal → kein tenant-weites Org-Chart-Broadcast.
        entry_department = department if current_user.role == UserRole.ADMIN else None
        calendar_entries.append(AbsenceCalendarEntry(
            date=absence.date,
            user_first_name=first_name,
            user_last_name=last_name,
            user_color=calendar_color,
            department=entry_department,
            type=display_type,
            hours=absence.hours
        ))

    return calendar_entries


@router.get("/team/upcoming", response_model=List[TeamAbsenceEntry])
def get_team_upcoming_absences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get upcoming absences for all active employees.
    Visible to all authenticated users.
    Shows unique absence periods (groups consecutive days with same end_date).
    """
    today = today_local()

    # Get all future absences from active users, fetching User columns in the same query
    rows = db.query(
        Absence, User.first_name, User.last_name, User.calendar_color
    ).join(User).filter(
        # F-026: explicit tenant scope on the tenant-wide upcoming-absences feed.
        Absence.tenant_id == current_user.tenant_id,
        User.is_active == True,
        User.is_hidden == False,
        Absence.date >= today
    ).order_by(Absence.date, User.last_name, User.first_name).all()

    # Group by user and end_date to avoid duplicates for date ranges
    seen = set()
    team_absences = []

    # #312: custom-reason labels (shown to admins/owners, masked for colleagues),
    # mirroring the /calendar feed. Key on str(id) (robust to UUID-vs-string).
    reason_names = {
        str(r.id): r.name for r in db.query(AbsenceReason.id, AbsenceReason.name)
        .filter(AbsenceReason.tenant_id == current_user.tenant_id).all()
    }

    # DSGVO Art. 9: Krankheitsdaten sind besonders schützenswert. Es muss
    # derselbe sensible Satz maskiert werden wie im /calendar-Feed
    # (_MASKED_ABSENCE_TYPES), sonst wäre "absent" hier ein 1:1-Indikator für
    # Krankheit (SICK→absent, während OTHER/PAID_LEAVE wahr blieben).
    for absence, first_name, last_name, calendar_color in rows:
        # Create a unique key for this absence period
        key = (absence.user_id, absence.date, absence.end_date or absence.date, absence.type)

        if key not in seen:
            seen.add(key)
            display_type = absence.type.value
            # #312: custom-reason absences are masked for non-admin colleagues too.
            masked = (
                (absence.type in _MASKED_ABSENCE_TYPES or absence.reason_id is not None)
                and current_user.role != UserRole.ADMIN
                and absence.user_id != current_user.id
            )
            if masked:
                display_type = "absent"
            elif absence.reason_id is not None:
                display_type = reason_names.get(str(absence.reason_id), display_type)
            team_absences.append(TeamAbsenceEntry(
                date=absence.date,
                end_date=absence.end_date,
                user_first_name=first_name,
                user_last_name=last_name,
                user_color=calendar_color,
                type=display_type,
                hours=absence.hours,
            ))

    return team_absences


@router.get("/next-vacation", response_model=Optional[NextVacationResponse])
def get_next_vacation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the next upcoming vacation for the current user.
    Returns the start date, optional end date, and days until the vacation.
    Returns null if no upcoming vacation is found.
    """
    today = today_local()

    next_vacation = db.query(Absence).filter(
        Absence.tenant_id == current_user.tenant_id,  # F-026: explizit, nicht nur RLS
        Absence.user_id == current_user.id,
        Absence.type == AbsenceType.VACATION,
        Absence.date >= today
    ).order_by(Absence.date.asc()).first()

    if not next_vacation:
        return None

    days_until = (next_vacation.date - today).days

    return NextVacationResponse(
        date=next_vacation.date,
        end_date=next_vacation.end_date,
        days_until=days_until
    )


@router.post("/", response_model=List[AbsenceResponse], status_code=status.HTTP_201_CREATED)
def create_absence(
    absence_data: AbsenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create absence entry/entries.
    If end_date is provided, creates entries for all weekdays (Mon-Fri) in the range.
    For vacation type, check if remaining vacation is sufficient.
    """

    # Determine target user (admin can create for others)
    target_user = current_user
    if absence_data.user_id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
        # F-026: explicit tenant scoping on admin cross-user absence creation
        target_user = db.query(User).filter(
            User.id == absence_data.user_id,
            User.tenant_id == current_user.tenant_id,
        ).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # #312: a custom absence reason determines the absence TYPE via its base
    # behaviour (the calculation runs on `type`). Resolve it up front so all
    # downstream type-specific logic uses the mapped built-in type; reason_id is
    # stored on the row for the display label/colour.
    reason_id = absence_data.reason_id
    if reason_id is not None:
        reason = db.query(AbsenceReason).filter(
            AbsenceReason.id == reason_id,
            AbsenceReason.tenant_id == current_user.tenant_id,  # F-026
            AbsenceReason.is_active.is_(True),
        ).first()
        if not reason:
            raise HTTPException(status_code=404, detail="Abwesenheitsgrund nicht gefunden oder inaktiv")
        try:
            absence_data.type = BEHAVIOR_TO_ABSENCE_TYPE[AbsenceReasonBehavior(reason.base_behavior)]
        except (KeyError, ValueError):
            raise HTTPException(status_code=400, detail="Ungültiges Basis-Verhalten des Abwesenheitsgrundes")

    # MA-ABS-01: Bei aktivierter Genehmigungspflicht dürfen NICHT-Admins Urlaub
    # nicht direkt buchen (sonst Approval-Bypass über die API) — sie müssen einen
    # Urlaubsantrag stellen. Admins (auch für sich) buchen weiterhin direkt. Greift
    # auch für eigene Gründe, die auf VACATION mappen (Auflösung steht oben).
    if (absence_data.type == AbsenceType.VACATION
            and current_user.role != UserRole.ADMIN
            and settings_service.get_bool_setting(
                db, "vacation_approval_required", current_user.tenant_id, False)):
        raise HTTPException(
            status_code=400,
            detail="Urlaub ist genehmigungspflichtig — bitte einen Urlaubsantrag stellen.",
        )

    # Determine date range
    start_date = absence_data.date
    end_date = absence_data.end_date if absence_data.end_date else absence_data.date

    # Validate date range (equal start/end is a valid single-day absence)
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="Enddatum darf nicht vor dem Startdatum liegen"
        )

    # Arbeitszeitraum-Prüfung (I2)
    if target_user.first_work_day and start_date < target_user.first_work_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Datum liegt vor dem ersten Arbeitstag ({target_user.first_work_day.strftime('%d.%m.%Y')})"
        )
    if target_user.last_work_day and end_date > target_user.last_work_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Datum liegt nach dem letzten Arbeitstag ({target_user.last_work_day.strftime('%d.%m.%Y')})"
        )

    # Generate list of weekdays (Mon-Fri, excluding weekends and holidays)
    dates_to_create = []
    current_date = start_date

    # Get holidays for the affected years
    years = set()
    temp_date = start_date
    while temp_date <= end_date:
        years.add(temp_date.year)
        temp_date += timedelta(days=1)

    holidays = set()
    for year in years:
        # F-026: explicit tenant scope on the standalone holiday lookup.
        year_holidays = db.query(PublicHoliday).filter(
            PublicHoliday.year == year,
            PublicHoliday.tenant_id == target_user.tenant_id,
        ).all()
        holidays.update([h.date for h in year_holidays])

    # Collect all weekdays in range (excluding weekends and holidays)
    while current_date <= end_date:
        # Check if it's a weekday (0=Monday, 6=Sunday)
        if current_date.weekday() < 5 and current_date not in holidays:
            dates_to_create.append(current_date)
        current_date += timedelta(days=1)

    if not dates_to_create:
        raise HTTPException(
            status_code=400,
            detail="Keine gültigen Arbeitstage im angegebenen Zeitraum"
        )

    # BUG-3 / Review 2026-06-23 (2. Schleife): die User-Zeile ZUERST sperren —
    # VOR den per-Datum-Absence-Locks unten — damit beide Urlaubs-Buchungspfade
    # (create_absence + review_vacation_request) dieselbe Lock-Reihenfolge
    # (User -> Absence) nutzen und kein ABBA-Deadlock moeglich ist. Der Lock
    # serialisiert zugleich den Budget-Check + Insert pro MA (kein Budget-Overrun).
    if absence_data.type == AbsenceType.VACATION:
        db.query(User).filter(User.id == target_user.id).with_for_update().first()

    # Check for existing absences (any type — no double-booking allowed).
    # F-028: with_for_update() on the existence probe closes the race window
    # between this check and the INSERT below. The DB-level unique constraint
    # is (tenant_id, user_id, date, type) — different types on the same day
    # would slip through without the row lock, causing double-booking.
    skip_dates = []
    for d in dates_to_create:
        existing = (
            db.query(Absence)
            .filter(
                Absence.user_id == target_user.id,
                Absence.tenant_id == target_user.tenant_id,
                Absence.date == d,
            )
            .with_for_update()
            .first()
        )

        if existing:
            if existing.type == absence_data.type:
                skip_dates.append(d)  # Skip duplicate of same type (idempotent)
            elif (
                absence_data.type == AbsenceType.SICK
                and absence_data.refund_vacation
                and existing.type == AbsenceType.VACATION
            ):
                # "Krank während Urlaub": die SICK-Buchung ersetzt den Urlaub an
                # diesem Tag. Der Refund-Block weiter unten löscht den VACATION-
                # Eintrag (mit Audit-Log), bevor die SICK-Abwesenheit angelegt
                # wird — daher hier KEIN 409. Ohne diese Ausnahme war
                # refund_vacation totes Feature: der Konflikt-Check schlug immer
                # vor der Urlaubsrückgabe zu (Code-Review 1.8.9, F-B).
                pass
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Am {d.strftime('%d.%m.%Y')} existiert bereits eine Abwesenheit ({existing.type.value})"
                )
    dates_to_create = [d for d in dates_to_create if d not in skip_dates]

    if not dates_to_create:
        raise HTTPException(
            status_code=400,
            detail="Alle Tage im Zeitraum haben bereits eine Abwesenheit dieses Typs"
        )

    # For vacation, check remaining vacation days (per year for cross-year ranges).
    # Die User-Zeile ist oben bereits per with_for_update gesperrt (BUG-3 +
    # ABBA-Fix) -> Budget-Check + Insert sind pro MA serialisiert.
    if absence_data.type == AbsenceType.VACATION:
        # Group dates by year for budget check
        dates_by_year = {}
        for d in dates_to_create:
            dates_by_year.setdefault(d.year, []).append(d)
        for check_year, year_dates in dates_by_year.items():
            vacation_account = calculation_service.get_vacation_account(db, target_user, check_year)
            # #156/T2 — Tagesprinzip: each booked working day consumes one vacation
            # day (0,5 for a half day, #167); compare the day COUNT against the
            # remaining DAYS, not hours (hours-based checks mis-block uneven
            # schedules / part-time).
            # R1-3: skip days with 0h daily target only when use_daily_schedule=True
            # (e.g. Mon/Wed/Fri user — Tuesday has 0h and is skipped by the creation
            # loop too). Only applies when track_hours=True; for track_hours=False users
            # all weekdays count (pure day-based booking, hours are always 0).
            # Pre-check must agree with what the booking actually consumes.
            if getattr(target_user, 'use_daily_schedule', False) and target_user.track_hours:
                billable_days = [
                    d for d in year_dates
                    if float(calculation_service.get_daily_target_for_date(
                        target_user, d,
                        weekly_hours=calculation_service.get_weekly_hours_for_date(db, target_user, d),
                    )) > 0
                ]
            else:
                billable_days = year_dates
            days_needed = len(billable_days) * (0.5 if absence_data.half_day else 1.0)
            if days_needed > vacation_account["remaining_days"] + 1e-9:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Nicht genügend Urlaubstage für {check_year} ({vacation_account['remaining_days']:.1f} Tage verfügbar)"
                )

    # If sick leave with vacation refund: remove overlapping vacation entries first
    refunded_vacation_dates = []
    if absence_data.type == AbsenceType.SICK and absence_data.refund_vacation:
        for date in dates_to_create:
            vacation_entry = db.query(Absence).filter(
                Absence.user_id == target_user.id,
                Absence.tenant_id == target_user.tenant_id,  # F-026
                Absence.date == date,
                Absence.type == AbsenceType.VACATION
            ).first()
            if vacation_entry:
                # Audit-Log: Urlaubsrückgabe dokumentieren
                audit_log = TimeEntryAuditLog(
                    time_entry_id=None,
                    user_id=target_user.id,
                    changed_by=current_user.id,
                    action="delete",
                    old_date=vacation_entry.date,
                    old_start_time=vacation_entry.start_time,
                    old_end_time=vacation_entry.end_time,
                    old_note=f"absence:{vacation_entry.type.value}:{float(vacation_entry.hours)}h",
                    source="vacation_refund",
                    tenant_id=current_user.tenant_id,
                )
                db.add(audit_log)
                db.delete(vacation_entry)
                refunded_vacation_dates.append(date)

    # Delete existing time entries on affected dates (unless keep_time_entries for mixed days)
    if not absence_data.keep_time_entries:
        existing_entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == target_user.id,
            TimeEntry.tenant_id == current_user.tenant_id,
            TimeEntry.date.in_(dates_to_create),
        ).all()
        for entry in existing_entries:
            _create_audit_log(
                db, entry.id, target_user.id, current_user.id,
                action="delete", old_entry=entry,
                source="absence_creation",
                tenant_id=current_user.tenant_id,
            )
            db.delete(entry)

    # Create absences for all dates
    created_absences = []
    for date in dates_to_create:
        # #156 Sofortmaßnahme: a full-day absence is always credited with the
        # employee's *own* scheduled daily target — never a caller-supplied value
        # (which the booking form defaults to 8h). That guarantees one absent
        # working day == exactly one day for everyone, regardless of contracted
        # daily hours (Teilzeit). §3 EntgFG requires this for SICK anyway.
        # Only OVERTIME compensation keeps its explicit hours (the amount of
        # overtime being drawn down), unless a per-weekday schedule applies.
        if absence_data.type != AbsenceType.OVERTIME or getattr(target_user, 'use_daily_schedule', False):
            weekly = calculation_service.get_weekly_hours_for_date(db, target_user, date)
            hours_for_day = float(calculation_service.get_daily_target_for_date(target_user, date, weekly_hours=weekly))
            # Review R3 (HIGH): only skip genuine 0h days for TRACKED users (e.g.
            # a Mo/Mi/Fr part-timer's Tue/Thu). For track_hours=False the daily
            # target is ALWAYS 0 — skipping here would create NO absence at all,
            # so the day-based vacation account (#191) never sees a row to count.
            # dates_to_create already excludes weekends/holidays, so every
            # remaining day must be booked (hours stay 0, counted day-based).
            if hours_for_day == 0 and target_user.track_hours:
                continue  # tracked user: scheduled non-working day → skip
            # #167: halber Tag = 0,5 × Tagessoll → zählt diskriminierungsfrei als 0,5
            # Urlaubstag (8h-Tag: 4h; 3h-Tag: 1,5h — je 0,5 Tag). Nicht für OVERTIME.
            if absence_data.half_day:
                hours_for_day = round(hours_for_day / 2, 2)
        else:
            hours_for_day = absence_data.hours

        absence = Absence(
            user_id=target_user.id,
            tenant_id=current_user.tenant_id,
            date=date,
            end_date=end_date if absence_data.end_date else None,  # Store end_date for reference
            type=absence_data.type,
            hours=hours_for_day,
            start_time=absence_data.start_time,
            end_time=absence_data.end_time,
            # #205: Buchungs-Intent persistieren -> tagebasierter, WHChange-stabiler
            # Urlaubsverbrauch (Voll-Tag False, Halbtag True). Bei Zeitraeumen ist
            # half_day per Schema False (Halbtag ist ein Einzeltag-Konzept).
            half_day=absence_data.half_day,
            note=absence_data.note,
            reason_id=reason_id,  # #312
        )
        db.add(absence)
        created_absences.append(absence)

    db.commit()

    # Refresh all created absences
    for absence in created_absences:
        db.refresh(absence)

    return created_absences


@router.delete("/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_absence(
    absence_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an absence entry."""
    # F-026: the rule explicitly requires an explicit tenant filter on .delete()
    # lookups, not RLS alone.
    absence = db.query(Absence).filter(
        Absence.id == absence_id,
        Absence.tenant_id == current_user.tenant_id,
    ).first()

    if not absence:
        raise HTTPException(status_code=404, detail="Abwesenheit nicht gefunden")

    # Check permissions
    if absence.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        # #120: 404 statt 403 — fremde (Same-Tenant-)Abwesenheit wird wie eine
        # unbekannte behandelt, kein Existenz-Leak via Response-Code.
        raise HTTPException(status_code=404, detail="Abwesenheit nicht gefunden")

    # DSGVO Art. 5 Abs. 2: Audit-Log vor Löschung
    audit = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=absence.user_id,
        changed_by=current_user.id,
        action="delete",
        old_date=absence.date,
        old_note=f"absence:{absence.type.value}:{float(absence.hours)}h",
        source="manual",
        tenant_id=current_user.tenant_id,
    )
    db.add(audit)

    db.delete(absence)
    db.commit()

    return None
