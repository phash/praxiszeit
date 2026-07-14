from datetime import date, datetime, timedelta
from app.services.timezone_service import today_local
from app.services.date_filters import date_in_year, date_in_month, date_in_range
from decimal import Decimal
from calendar import monthrange
from typing import Dict, List, NamedTuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.models import User, TimeEntry, Absence, AbsenceReason, PublicHoliday, AbsenceType, WorkingHoursChange, YearCarryover
from app.services import special_days_service, settings_service


def get_weekly_hours_for_date(
    db: Session,
    user: User,
    target_date: date,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Decimal:
    """
    Get the weekly hours that were valid for a specific date.
    Considers historical working hours changes.

    This is the SINGLE authoritative lookup — other call-sites must NEVER
    read ``user.weekly_hours`` directly (CLAUDE.md rule). Hot-path callers
    that need many lookups per request may pass a pre-loaded ``wh_changes``
    list to avoid one SELECT per day; the change-search is then performed
    in memory with identical semantics.

    Args:
        db: Database session (unused when wh_changes is provided)
        user: User object
        target_date: Date to get hours for
        wh_changes: Optional pre-loaded list of WorkingHoursChange for this
            user. When supplied, no DB query is issued. Must be filtered to
            ``user_id == user.id`` by the caller — this function does not
            re-filter.

    Returns:
        Weekly hours as Decimal
    """
    if wh_changes is None:
        # Classic path: one DB query, always correct.
        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user.id,
            WorkingHoursChange.effective_from <= target_date
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
    else:
        # In-memory path: scan the pre-loaded list. We mirror the SQL
        # ``ORDER BY effective_from DESC LIMIT 1`` semantics exactly.
        change = None
        for c in wh_changes:
            if c.effective_from <= target_date and (
                change is None or c.effective_from > change.effective_from
            ):
                change = c

    if change:
        return Decimal(str(change.weekly_hours))

    # No historical change found — fall back to the current user value.
    # This is the ONLY place in the codebase that may read user.weekly_hours
    # directly; everything else must route through this helper.
    return Decimal(str(user.weekly_hours))


def get_daily_target(user: User, weekly_hours: Decimal = None) -> Decimal:
    """
    Calculate daily target hours based on weekly hours and work days.

    Formula: weekly_hours / work_days_per_week

    Examples:
    - 20h at 2 days → 10h/day
    - 20h at 5 days → 4h/day
    - 40h at 5 days → 8h/day

    NOTE: Does NOT consider per-day schedule. Use get_daily_target_for_date()
    for date-aware calculations.

    Args:
        user: User object
        weekly_hours: Optional weekly hours to use (if None, uses user.weekly_hours)

    Returns:
        Daily target hours as Decimal (0 if track_hours is False)
    """
    if not user.track_hours:
        return Decimal('0')

    if weekly_hours is None:
        weekly_hours = Decimal(str(user.weekly_hours))

    # Use work_days_per_week instead of hardcoded 5
    work_days = Decimal(str(user.work_days_per_week))

    if work_days == 0:  # Safety check
        return Decimal('0')

    return (weekly_hours / work_days).quantize(Decimal('0.01'))


def get_daily_target_for_date(user: User, target_date: date, weekly_hours: Decimal = None) -> Decimal:
    """
    Calculate daily target hours for a specific date.

    If user has use_daily_schedule=True, returns the hours configured
    for that specific weekday (Mon–Fri). Weekends always return 0.

    If use_daily_schedule=False, falls back to get_daily_target().

    Args:
        user: User object
        target_date: The specific date
        weekly_hours: Optional weekly hours override (used when use_daily_schedule=False)

    Returns:
        Daily target hours as Decimal
    """
    if not user.track_hours:
        return Decimal('0')

    weekday = target_date.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

    if weekday >= 5:
        return Decimal('0')

    if getattr(user, 'use_daily_schedule', False):
        day_columns = [
            user.hours_monday,
            user.hours_tuesday,
            user.hours_wednesday,
            user.hours_thursday,
            user.hours_friday,
        ]
        day_hours = day_columns[weekday]
        if day_hours is None:
            return Decimal('0')
        return Decimal(str(day_hours)).quantize(Decimal('0.01'))

    return get_daily_target(user, weekly_hours)


def fixed_monthly_target(user: User, year: int, month: int) -> Decimal:
    """#377 Baustein 2b: festes Monats-Soll = agreed_monthly_hours, anteilig bei
    Eintritt/Austritt (Kalendertag-Bruchteil des Beschäftigungsfensters im Monat).
    Gibt 0, wenn der Modus aus ist oder agreed fehlt (Caller → wie Modus aus)."""
    agreed = getattr(user, "agreed_monthly_hours", None)
    if not getattr(user, "use_fixed_monthly_target", False) or not agreed or Decimal(str(agreed)) <= 0:
        return Decimal('0')
    agreed = Decimal(str(agreed))
    days_in_month = monthrange(year, month)[1]
    in_window = sum(
        1 for day in range(1, days_in_month + 1)
        if _within_employment_window(user, date(year, month, day))
    )
    if in_window == 0:
        return Decimal('0')
    if in_window == days_in_month:
        return agreed.quantize(Decimal('0.01'))
    return (agreed * Decimal(in_window) / Decimal(days_in_month)).quantize(Decimal('0.01'))


# #377 Baustein 2b: bezahlte Fehltag-Typen, die im Fix-Modus geplante Stunden dem
# Ist gutschreiben. SICK/TRAINING NICHT hier — die laufen über credited_absences
# (get_range_actual); erneut addieren wäre Doppelgutschrift.
_FIXED_PAID_CREDIT_TYPES = frozenset({AbsenceType.VACATION, AbsenceType.PAID_LEAVE})
# unbezahlt entschuldigt → mindert das feste Soll.
_FIXED_UNPAID_TYPES = frozenset({AbsenceType.OTHER})


def _fixed_planned_hours(db: Session, user: User, d: date, special_cfg: dict) -> Decimal:
    """Geplante Tagesstunden an ``d`` (0 an ungeplanten Tagen/Wochenende), inkl.
    #394-Sondertags-/Halbtags-Faktor. Nur im use_daily_schedule-Sinn sinnvoll."""
    weekly = get_weekly_hours_for_date(db, user, d)
    planned = get_daily_target_for_date(user, d, weekly)
    if planned <= 0:
        return Decimal('0')
    return (planned * half_special_day_weight(d, special_cfg))


def _fixed_month_absence_hours(db, user, year, month, types, up_to_date, include_holidays):
    """Gemeinsame Schleife: Σ geplante Stunden für Tage mit einem passenden
    ganztägigen Absence-Typ (bzw. Feiertag, wenn include_holidays), im Fenster,
    ≤ up_to_date, ohne konkurrierenden TimeEntry (reale Erfassung gewinnt)."""
    days_in_month = monthrange(year, month)[1]
    cfg = special_days_service.get_special_day_config(db, user.tenant_id, year)
    holiday_dates = set()
    if include_holidays:
        holiday_dates = {h.date for h in db.query(PublicHoliday).filter(
            date_in_month(PublicHoliday.date, year, month),
            PublicHoliday.tenant_id == user.tenant_id,
        ).all()}
    absences = {a.date: a for a in db.query(Absence).filter(
        Absence.user_id == user.id, Absence.tenant_id == user.tenant_id,
        date_in_month(Absence.date, year, month),
        Absence.type.in_(list(types)), Absence.start_time.is_(None),  # nur ganztägig
    ).all()}
    entry_dates = {e.date for e in db.query(TimeEntry.date).filter(
        TimeEntry.user_id == user.id, TimeEntry.tenant_id == user.tenant_id,
        date_in_month(TimeEntry.date, year, month),
    ).all()}
    total = Decimal('0')
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if up_to_date is not None and d > up_to_date:
            continue
        if not _within_employment_window(user, d):
            continue
        if d in entry_dates:
            continue  # reale Erfassung gewinnt
        a = absences.get(d)
        is_holiday = include_holidays and d in holiday_dates
        if not a and not is_holiday:
            continue
        planned = _fixed_planned_hours(db, user, d, cfg)
        if a is not None and a.half_day:
            planned = planned * Decimal('0.5')
        total += planned
    return total.quantize(Decimal('0.01'))


def fixed_month_credit(db: Session, user: User, year: int, month: int, up_to_date: date = None) -> Decimal:
    """#377 Baustein 2b: geplante Stunden, die BEZAHLTE Fehltage (Feiertag +
    VACATION/PAID_LEAVE) dem Ist gutschreiben. SICK/TRAINING NICHT (Doppelguard)."""
    if not getattr(user, "use_fixed_monthly_target", False):
        return Decimal('0')
    return _fixed_month_absence_hours(db, user, year, month, _FIXED_PAID_CREDIT_TYPES,
                                      up_to_date, include_holidays=True)


def fixed_month_unpaid_reduction(db: Session, user: User, year: int, month: int, up_to_date: date = None) -> Decimal:
    """#377 Baustein 2b: geplante Stunden UNBEZAHLTER Fehltage (OTHER), die das
    feste Monats-Soll mindern (statt Ist+)."""
    if not getattr(user, "use_fixed_monthly_target", False):
        return Decimal('0')
    return _fixed_month_absence_hours(db, user, year, month, _FIXED_UNPAID_TYPES,
                                      up_to_date, include_holidays=False)


def get_working_days_in_month(db: Session, year: int, month: int) -> int:
    """
    Calculate number of working days (Mon-Fri) in a month.
    Excludes weekends but does NOT exclude holidays or absences.

    Args:
        db: Database session (unused, kept for consistency)
        year: Year
        month: Month (1-12)

    Returns:
        Number of working days (weekdays)
    """
    _, last_day = monthrange(year, month)
    working_days = 0

    for day in range(1, last_day + 1):
        d = date(year, month, day)
        # Count only weekdays (Mon-Fri)
        if d.weekday() < 5:
            working_days += 1

    return working_days


# NOTE: §3 ArbZG allows extending daily work to 10h if compensated to 8h average
# within 6 calendar months / 24 weeks. This averaging period is not tracked
# automatically — it requires manual monitoring by the employer.


def _within_employment_window(user: User, d: date) -> bool:
    """#193: True if ``d`` lies within the user's employment window.

    Days before ``first_work_day`` or after ``last_work_day`` contribute no
    target — the user was not employed then. Mirrors the pro-rata logic already
    used in get_vacation_account so Soll- and Urlaubsberechnung stay consistent.
    Open bounds when the respective field is unset.
    """
    if user.first_work_day and d < user.first_work_day:
        return False
    if user.last_work_day and d > user.last_work_day:
        return False
    return True


def _soll_reducing_absence_half_map(absences: List[Absence]) -> Dict[date, bool]:
    """Fix #1: map each soll-reducing absence (VACATION/OTHER/PAID_LEAVE) date to
    whether it is a HALF day, for the shared per-day Soll helper below.

    Value semantics:

    * date NOT in map → no soll-reducing absence that day (full Tagessoll counts)
    * value ``False`` → full-day absence → the whole day's Soll is removed
    * value ``True``  → half-day absence → only 0,5 × Tagessoll is removed
                        (half the Soll remains so the worked half still counts)

    ``half_day`` only counts as half when explicitly ``True``; legacy rows
    (``None``) and full-day rows (``False``) keep the historic full-skip
    behaviour. If two rows ever shared a date (the unique constraint normally
    prevents it), a full day wins (more Soll removed = conservative).
    """
    m: Dict[date, bool] = {}
    for a in absences:
        is_half = a.half_day is True
        m[a.date] = (m[a.date] and is_half) if a.date in m else is_half
    return m


def _day_soll_contribution(
    db: Session,
    user: User,
    d: date,
    *,
    holiday_dates: set,
    absence_half_map: Dict[date, bool],
    wh_changes: Optional[List[WorkingHoursChange]],
    special_cfg: dict,
) -> Decimal:
    """Fix #1: single source of truth for ONE weekday's Soll contribution, shared
    by all four per-day Soll loops (get_range_target, get_overtime_account,
    get_overtime_history, get_ytd_summary) so half-day handling never diverges.

    The CALLER is responsible for the weekend / employment-window / up_to_date
    cutoff skips. This helper handles, in order: holidays, soll-reducing
    absences (full vs. half day), the per-date weekly-hours lookup, the #146
    special-day factor and finally the half-day halving — special-day factor
    FIRST, then ×0,5 for a half day. Returns 0 for a holiday or a full-day
    soll-reducing absence.
    """
    if d in holiday_dates:
        return Decimal('0')
    half = absence_half_map.get(d)
    if half is False:
        return Decimal('0')  # full-day soll-reducing absence → no Soll this day
    weekly_hours = get_weekly_hours_for_date(db, user, d, wh_changes=wh_changes)
    daily_target = get_daily_target_for_date(user, d, weekly_hours)
    factor = special_days_service.special_day_target_factor(d, special_cfg)
    if factor is not None:
        daily_target = daily_target * factor
    if half is True:
        daily_target = daily_target * Decimal('0.5')
    return daily_target


def get_soll_cutoff_date(db: Session, user: User, today: date = None) -> date:
    """#313: last date (inclusive) that counts toward the running Soll/Ist.

    ``today`` counts only once it is a *completed* workday — i.e. a clocked-out
    ``TimeEntry`` exists for today; otherwise the cutoff is *yesterday*. This way
    the running month no longer starts on the 1st with the whole month's Soll as
    a deficit; the balance is built up to the last finished working day.
    """
    if today is None:
        today = today_local()
    has_completed_today = db.query(TimeEntry.id).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        TimeEntry.date == today,
        TimeEntry.end_time.isnot(None),
    ).first() is not None
    return today if has_completed_today else today - timedelta(days=1)


def get_range_target(
    db: Session, user: User, start: date, end: date, up_to_date: date = None
) -> Decimal:
    """Soll hours for an arbitrary inclusive ``[start, end]`` range.

    Same per-day logic as :func:`get_monthly_target` (skip weekends / public
    holidays / soll-reducing absences, respect the employment window #193 and the
    #313 ``up_to_date`` cutoff, apply the #146 special-day factor), but over a
    range that may cross a month or year boundary. ``get_monthly_target``
    delegates here so there is a single source of truth.

    Absences REDUCE the target (the employee need not work those days), except
    TRAINING/SICK/OVERTIME (credited / Überstundenausgleich — see
    get_monthly_target's original note). The special-day config is fetched per
    year so a range spanning Dec/Jan stays correct.

    Returns 0 if ``track_hours`` is False or the range is empty.
    """
    if not user.track_hours or end < start:
        return Decimal('0')

    # F-033: sargable date range.
    holidays = db.query(PublicHoliday).filter(
        date_in_range(PublicHoliday.date, start, end),
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()
    holiday_dates = {h.date for h in holidays}

    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        date_in_range(Absence.date, start, end),
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    # Fix #1: half-day-aware map (full day → skip, half day → halve Soll).
    absence_half_map = _soll_reducing_absence_half_map(absences)

    # Preload the user's WorkingHoursChange rows ONCE and resolve the per-day
    # weekly hours in memory (avoids one SELECT per day — N+1 — for a multi-day
    # range; mirrors get_overtime_account). F-026: tenant-scoped.
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,
    ).order_by(WorkingHoursChange.effective_from).all()

    # #146: special-day config can differ per year (a week may cross Dec/Jan).
    _special_cfg_cache: dict = {}

    def _special_cfg(yr: int) -> dict:
        if yr not in _special_cfg_cache:
            _special_cfg_cache[yr] = special_days_service.get_special_day_config(
                db, user.tenant_id, yr
            )
        return _special_cfg_cache[yr]

    total = Decimal('0')
    d = start
    while d <= end:
        # Skip weekends
        if d.weekday() >= 5:  # Saturday or Sunday
            d += timedelta(days=1)
            continue
        # #313: only count up to the running cutoff (e.g. last finished workday)
        if up_to_date is not None and d > up_to_date:
            d += timedelta(days=1)
            continue
        # #193: skip days outside the employment window (before entry / after exit)
        if not _within_employment_window(user, d):
            d += timedelta(days=1)
            continue

        # Fix #1: holidays / soll-reducing absences (full vs. half day) + the #146
        # special-day factor live in the shared per-day helper so all four Soll
        # loops behave identically (full-day absence → 0; half-day → 0,5×Soll).
        total += _day_soll_contribution(
            db, user, d,
            holiday_dates=holiday_dates,
            absence_half_map=absence_half_map,
            wh_changes=wh_changes,
            special_cfg=_special_cfg(d.year),
        )
        d += timedelta(days=1)

    return total.quantize(Decimal('0.01'))


def get_range_actual(
    db: Session, user: User, start: date, end: date, up_to_date: date = None
) -> Decimal:
    """Ist hours worked in an arbitrary inclusive ``[start, end]`` range.

    Sum of TimeEntry net_hours + credited TRAINING/SICK hours, both windowed by
    the employment window (#195) and the optional ``up_to_date`` cutoff.
    ``get_monthly_actual`` delegates here.
    """
    if end < start:
        return Decimal('0')

    # F-033: sargable date range. The Python-level Decimal sum is kept because
    # the SQL @expression for net_hours relies on Postgres EXTRACT(EPOCH ...)
    # semantics that do not port to the SQLite test suite.
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        date_in_range(TimeEntry.date, start, end),
    ).all()
    # #195: only count Ist within the employment window — symmetric to the Soll
    # guard. A TimeEntry before first_work_day / after last_work_day must
    # contribute neither Soll nor Ist, otherwise the balance shows phantom overtime.
    total = sum((entry.net_hours for entry in entries
                 if _within_employment_window(user, entry.date)
                 and (up_to_date is None or entry.date <= up_to_date)), start=Decimal('0'))

    # Training and sick hours count as actual worked hours (außer Haus / §3 EntgFG).
    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
        date_in_range(Absence.date, start, end),
    ).all()
    credited_hours = sum((Decimal(str(a.hours)) for a in credited_absences
                          if _within_employment_window(user, a.date)
                          and (up_to_date is None or a.date <= up_to_date)), Decimal('0'))

    return (Decimal(str(total)) + credited_hours).quantize(Decimal('0.01'))


def get_monthly_target(
    db: Session, user: User, year: int, month: int, up_to_date: date = None
) -> Decimal:
    """
    Calculate monthly target hours (thin wrapper over :func:`get_range_target`).

    For each weekday (Mon-Fri) in the month: skip public holidays + soll-reducing
    absences, add the daily target (based on the weekly hours valid for that date,
    so a mid-month WorkingHoursChange is handled correctly). Absences REDUCE the
    target. Returns 0 if track_hours is False.
    """
    _, last_day = monthrange(year, month)
    return get_range_target(
        db, user, date(year, month, 1), date(year, month, last_day), up_to_date=up_to_date
    )


def get_monthly_actual(
    db: Session, user: User, year: int, month: int, up_to_date: date = None
) -> Decimal:
    """
    Calculate actual hours worked in a month (thin wrapper over
    :func:`get_range_actual`). Sum of TimeEntry net_hours + credited
    TRAINING/SICK hours (§3 EntgFG / Fortbildung außer Haus).
    """
    _, last_day = monthrange(year, month)
    return get_range_actual(
        db, user, date(year, month, 1), date(year, month, last_day), up_to_date=up_to_date
    )


def get_gross_monthly_target(db: Session, user: User, year: int, month: int) -> Decimal:
    """Gross monthly target — like get_monthly_target but WITHOUT subtracting the
    soll-reducing absence days (VACATION/OTHER/PAID_LEAVE). Weekend, holiday,
    employment-window (#193) and special-day factor (#146) are still applied.

    Used ONLY by the classic yearly report, which presents the traditional
    "Brutto-Soll − Krank − Urlaub = bereinigtes Soll" layout: the explicit
    "minus" rows are the ones that reduce the soll there, so row 7 must be the
    gross value (get_monthly_target already nets vacation/other/paid_leave out).
    """
    if not user.track_hours:
        return Decimal('0')

    holiday_dates = {h.date for h in db.query(PublicHoliday).filter(
        date_in_month(PublicHoliday.date, year, month),
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()}
    special_day_config = special_days_service.get_special_day_config(db, user.tenant_id, year)

    _, last_day = monthrange(year, month)
    gross = Decimal('0')
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        if d.weekday() >= 5:
            continue
        if not _within_employment_window(user, d):
            continue
        if d in holiday_dates:
            continue
        weekly_hours = get_weekly_hours_for_date(db, user, d)
        daily_target = get_daily_target_for_date(user, d, weekly_hours)
        factor = special_days_service.special_day_target_factor(d, special_day_config)
        if factor is not None:
            daily_target = daily_target * factor
        gross += daily_target

    return gross.quantize(Decimal('0.01'))


def get_monthly_worked_hours(db: Session, user: User, year: int, month: int) -> Decimal:
    """Hours physically WORKED (Σ net_hours of time entries, employment-windowed)
    — WITHOUT the credited TRAINING/SICK hours that get_monthly_actual adds.

    Used by the classic yearly report's "erbrachte Stunden" row, whose
    traditional gross-model balance compares worked-only against the
    absence-reduced soll. NOT a substitute for get_monthly_actual anywhere else.
    """
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        date_in_month(TimeEntry.date, year, month),
    ).all()
    total = sum((entry.net_hours for entry in entries
                 if _within_employment_window(user, entry.date)), start=Decimal('0'))
    return Decimal(str(total)).quantize(Decimal('0.01'))


def get_monthly_balance(
    db: Session, user: User, year: int, month: int, up_to_date: date = None
) -> Decimal:
    """
    Calculate monthly balance (Actual - Target).

    Args:
        db: Database session
        user: User object
        year: Year
        month: Month (1-12)

    Returns:
        Monthly balance as Decimal (positive = overtime, negative = deficit)
    """
    target = get_monthly_target(db, user, year, month, up_to_date=up_to_date)
    actual = get_monthly_actual(db, user, year, month, up_to_date=up_to_date)

    balance = actual - target

    return balance.quantize(Decimal('0.01'))


def get_overtime_account(
    db: Session, user: User, up_to_year: int, up_to_month: int, cutoff_date: date = None
) -> Decimal:
    """
    Calculate cumulative overtime account up to specified month.

    If a YearCarryover exists, uses it as the starting balance and only
    iterates months from that year forward (avoids double-counting).
    Otherwise falls back to calculating from the first time entry.

    Args:
        db: Database session
        user: User object
        up_to_year: Year to calculate up to (inclusive)
        up_to_month: Month to calculate up to (inclusive)

    Returns:
        Cumulative overtime as Decimal
    """
    if not user.track_hours:
        return Decimal('0.00')

    up_to_date = date(up_to_year, up_to_month, monthrange(up_to_year, up_to_month)[1])

    # --- determine starting point ---
    # Find the most recent carryover at or before up_to_year
    latest_carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year <= up_to_year,
    ).order_by(YearCarryover.year.desc()).first()

    if latest_carryover:
        # Start from Jan of the carryover year with the carryover value
        start_year = latest_carryover.year
        start_month = 1
        initial_balance = Decimal(str(latest_carryover.overtime_hours))
        start_date = date(start_year, 1, 1)
    else:
        # No carryover: start from first time entry
        first_entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id
        ).order_by(TimeEntry.date).first()

        if not first_entry:
            return Decimal('0.00')

        start_year = first_entry.date.year
        start_month = first_entry.date.month
        initial_balance = Decimal('0.00')
        start_date = date(start_year, start_month, 1)

    # --- single-pass bulk fetches ---
    # All time entries in range (group by month in memory)
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start_date,
        TimeEntry.date <= up_to_date,
    ).all()
    # #195: skip Ist outside the employment window (symmetric to the Soll guard
    # in the month loop below) so out-of-window entries don't create phantom
    # overtime.
    actual_by_month: Dict[tuple, Decimal] = {}
    for e in entries:
        if not _within_employment_window(user, e.date):
            continue
        if cutoff_date is not None and e.date > cutoff_date:  # #313
            continue
        key = (e.date.year, e.date.month)
        actual_by_month[key] = actual_by_month.get(key, Decimal('0')) + Decimal(str(e.net_hours))

    # Training and sick hours count as actual worked hours (§3 EntgFG)
    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all()
    for ca in credited_absences:
        if not _within_employment_window(user, ca.date):
            continue
        if cutoff_date is not None and ca.date > cutoff_date:  # #313
            continue
        key = (ca.date.year, ca.date.month)
        actual_by_month[key] = actual_by_month.get(key, Decimal('0')) + Decimal(str(ca.hours))

    # All absences in range (exclude TRAINING, SICK, OVERTIME — same rule as
    # get_monthly_target). VACATION/OTHER/PAID_LEAVE reduce the target and are
    # therefore balance-neutral (target drops, actual unaffected). PAID_LEAVE
    # (#145) is intentionally treated exactly like OTHER here.
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    # Fix #1: half-day-aware map (full day → skip, half day → halve Soll).
    absence_half_map: Dict[date, bool] = _soll_reducing_absence_half_map(absences)

    # All public holidays in range
    holidays = db.query(PublicHoliday).filter(
        PublicHoliday.date >= start_date,
        PublicHoliday.date <= up_to_date,
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()
    holiday_dates: set[date] = {h.date for h in holidays}

    # All working-hours changes for this user (pre-loaded for the hot loop).
    # F-027: routed through get_weekly_hours_for_date() with in-memory path
    # to satisfy the CLAUDE.md invariant "never read user.weekly_hours
    # directly" without paying the per-day DB-query cost.
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
    ).order_by(WorkingHoursChange.effective_from).all()

    # #146: special-day configs are per-year; cache them across the month loop
    # so a multi-year overtime calculation issues one settings query per year.
    special_day_configs: Dict[int, dict] = {}

    def _special_day_config(yr: int) -> dict:
        cfg = special_day_configs.get(yr)
        if cfg is None:
            cfg = special_days_service.get_special_day_config(db, user.tenant_id, yr)
            special_day_configs[yr] = cfg
        return cfg

    # --- iterate months and compute balance in memory ---
    total_balance = initial_balance
    current_year, current_month = start_year, start_month

    while (current_year < up_to_year) or (current_year == up_to_year and current_month <= up_to_month):
        key = (current_year, current_month)

        # Monthly target (mirrors get_monthly_target logic)
        _, last_day = monthrange(current_year, current_month)
        cfg = _special_day_config(current_year)
        monthly_target = Decimal('0')
        for day in range(1, last_day + 1):
            d = date(current_year, current_month, day)
            if d.weekday() >= 5:
                continue
            # #313: only count Soll up to the running cutoff (last finished workday)
            if cutoff_date is not None and d > cutoff_date:
                continue
            # #193: skip days outside the employment window (before entry / after exit)
            if not _within_employment_window(user, d):
                continue
            # Fix #1: shared per-day helper (full-day absence → 0; half-day →
            # 0,5×Soll; holiday → 0; #146 special-day factor applied first).
            monthly_target += _day_soll_contribution(
                db, user, d,
                holiday_dates=holiday_dates,
                absence_half_map=absence_half_map,
                wh_changes=wh_changes,
                special_cfg=cfg,
            )

        monthly_actual = actual_by_month.get(key, Decimal('0'))
        total_balance += (monthly_actual - monthly_target)

        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1

    return total_balance.quantize(Decimal('0.01'))


class MonthlyOvertime(NamedTuple):
    """Per-Monat-Aufschlüsselung aus :func:`get_overtime_history_detailed`.

    ``target``/``actual`` sind auf 0.01 quantisiert und damit bitgleich zu
    :func:`get_monthly_target` / :func:`get_monthly_actual` (gleicher cutoff);
    ``cumulative`` ist bitgleich zu :func:`get_overtime_account`.
    """
    target: Decimal
    actual: Decimal
    cumulative: Decimal


def get_overtime_history_detailed(
    db: Session, user: User, up_to_year: int, up_to_month: int, cutoff_date: date = None
) -> Dict[tuple, "MonthlyOvertime"]:
    """Soll/Ist/Konto NACH jedem Monat (Start..up_to) in EINEM Pass.

    Liefert je Monat (y, m) ein :class:`MonthlyOvertime` mit ``target``,
    ``actual`` und ``cumulative``. Invarianten (gepinnt):
        detailed[(y, m)].cumulative == get_overtime_account(db, user, y, m)
        detailed[(y, m)].target     == get_monthly_target(db, user, y, m)
        detailed[(y, m)].actual     == get_monthly_actual(db, user, y, m)
    (jeweils mit demselben cutoff_date).

    #150 / Fix #3: damit baut das Dashboard Soll/Ist/Saldo/Konto je Monat aus
    EINEM Single-Pass — statt get_monthly_target + get_monthly_actual ZUSÄTZLICH
    pro Monat zu rufen (jede Einzelrufung iteriert neu -> O(Monate²)).
    :func:`get_overtime_history` ist ein dünner Wrapper, der nur ``cumulative``
    zurückgibt (alter Vertrag + Invariante unverändert). Leeres Dict bei
    track_hours=False / keinen Daten.

    Wie get_overtime_account ist ein YearCarryover ein Reset-Punkt: im Januar
    eines Jahres MIT eigenem Carryover startet der laufende Saldo neu vom
    Carryover-Wert (spiegelt die "latest carryover <= year"-Auswahl der
    Einzelfunktion).
    """
    if not user.track_hours:
        return {}

    up_to_date = date(up_to_year, up_to_month, monthrange(up_to_year, up_to_month)[1])

    carryovers: Dict[int, Decimal] = {
        c.year: Decimal(str(c.overtime_hours))
        for c in db.query(YearCarryover).filter(YearCarryover.user_id == user.id).all()
    }

    first_entry = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id
    ).order_by(TimeEntry.date).first()
    if first_entry is None and not carryovers:
        return {}

    if first_entry is not None:
        fe_year, fe_month = first_entry.date.year, first_entry.date.month
    else:
        fe_year, fe_month = min(carryovers), 1

    # Start-Punkt = der Carryover, den get_overtime_account fuer den ersten Monat
    # waehlen wuerde (latest <= fe_year), sonst der erste Time-Entry.
    applicable = [y for y in carryovers if y <= fe_year]
    if applicable:
        start_year, start_month = max(applicable), 1
        initial_balance = carryovers[start_year]
    else:
        start_year, start_month = fe_year, fe_month
        initial_balance = Decimal('0.00')

    start_date = date(start_year, start_month, 1)

    # --- ein Bulk-Fetch ueber den ganzen Bereich (wie get_overtime_account) ---
    actual_by_month: Dict[tuple, Decimal] = {}
    for e in db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start_date,
        TimeEntry.date <= up_to_date,
    ).all():
        if not _within_employment_window(user, e.date):
            continue
        if cutoff_date is not None and e.date > cutoff_date:  # #313
            continue
        k = (e.date.year, e.date.month)
        actual_by_month[k] = actual_by_month.get(k, Decimal('0')) + Decimal(str(e.net_hours))

    for ca in db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all():
        if not _within_employment_window(user, ca.date):
            continue
        if cutoff_date is not None and ca.date > cutoff_date:  # #313
            continue
        k = (ca.date.year, ca.date.month)
        actual_by_month[k] = actual_by_month.get(k, Decimal('0')) + Decimal(str(ca.hours))

    # Fix #1: half-day-aware map (full day → skip, half day → halve Soll).
    absence_half_map = _soll_reducing_absence_half_map(db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all())

    holiday_dates = {h.date for h in db.query(PublicHoliday).filter(
        PublicHoliday.date >= start_date,
        PublicHoliday.date <= up_to_date,
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()}

    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
    ).order_by(WorkingHoursChange.effective_from).all()

    special_day_configs: Dict[int, dict] = {}

    def _cfg(yr: int) -> dict:
        c = special_day_configs.get(yr)
        if c is None:
            c = special_days_service.get_special_day_config(db, user.tenant_id, yr)
            special_day_configs[yr] = c
        return c

    history: Dict[tuple, MonthlyOvertime] = {}
    total_balance = initial_balance
    cy, cm = start_year, start_month

    while (cy < up_to_year) or (cy == up_to_year and cm <= up_to_month):
        # Reset im Januar eines Jahres mit eigenem Carryover (ausser dem Start).
        if cm == 1 and cy in carryovers and (cy, cm) != (start_year, start_month):
            total_balance = carryovers[cy]

        _, last_day = monthrange(cy, cm)
        cfg = _cfg(cy)
        monthly_target = Decimal('0')
        for day in range(1, last_day + 1):
            d = date(cy, cm, day)
            if d.weekday() >= 5:
                continue
            if cutoff_date is not None and d > cutoff_date:  # #313
                continue
            if not _within_employment_window(user, d):
                continue
            # Fix #1: shared per-day helper (kept bit-identical with
            # get_overtime_account so the history invariant holds).
            monthly_target += _day_soll_contribution(
                db, user, d,
                holiday_dates=holiday_dates,
                absence_half_map=absence_half_map,
                wh_changes=wh_changes,
                special_cfg=cfg,
            )

        monthly_actual = actual_by_month.get((cy, cm), Decimal('0'))
        total_balance += (monthly_actual - monthly_target)
        # cumulative wird (wie zuvor) aus den UNquantisierten Monatswerten
        # akkumuliert und erst beim Speichern quantisiert -> bitgleich zu
        # get_overtime_account. target/actual zusätzlich auf 0.01 quantisiert,
        # damit sie get_monthly_target/get_monthly_actual exakt entsprechen.
        history[(cy, cm)] = MonthlyOvertime(
            target=monthly_target.quantize(Decimal('0.01')),
            actual=monthly_actual.quantize(Decimal('0.01')),
            cumulative=total_balance.quantize(Decimal('0.01')),
        )

        if cm == 12:
            cm = 1
            cy += 1
        else:
            cm += 1

    return history


def get_overtime_history(
    db: Session, user: User, up_to_year: int, up_to_month: int, cutoff_date: date = None
) -> Dict[tuple, Decimal]:
    """Kumulatives Überstundenkonto NACH jedem Monat (Start..up_to) in EINEM Pass.

    Invariante: für jeden Monat (y, m) im Bereich gilt
        get_overtime_history(...)[(y, m)] == get_overtime_account(db, user, y, m)
    (gepinnt durch test_overtime_history_matches_account). Dünner Wrapper um
    :func:`get_overtime_history_detailed` — gibt nur den kumulativen Saldo
    zurück (alter Vertrag unverändert).
    """
    return {
        k: v.cumulative
        for k, v in get_overtime_history_detailed(
            db, user, up_to_year, up_to_month, cutoff_date=cutoff_date
        ).items()
    }


def get_ytd_summary(
    db: Session,
    user: User,
    year: int = None,
    cutoff_date: date = None,
    holidays: Optional[set] = None,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Dict:
    """
    Calculate year-to-date summary from Jan 1 to today.

    #204: ``holidays`` (tenant+year-Set) und ``wh_changes`` (dieses Users) sind
    optionale Preloads für den users-overview-Hot-Loop; Default ``None`` = wie
    bisher querien (byte-identisch, Test ``test_calc_preload``). Der YTD-Range
    liegt immer im Jahr ``year`` → das Jahres-Holiday-Set ist ein deckungsgleicher
    Superset für die Membership-Tests.

    Sums daily targets and actual hours for all working days from Jan 1
    of the given year up to and including today.

    Args:
        db: Database session
        user: User object
        year: Year (default: current year)

    Returns:
        Dict with target_hours, actual_hours, overtime
    """
    if not user.track_hours:
        return {"target_hours": 0.0, "actual_hours": 0.0, "overtime": 0.0}

    today = today_local()
    if year is None:
        year = today.year

    # End date: today if current year, else Dec 31.
    # #313: when a cutoff is given, the running year ends at the cutoff (= last
    # finished workday) instead of always "today", so the YTD-Soll doesn't
    # include today before it's a completed workday.
    if year == today.year:
        end = cutoff_date if cutoff_date is not None else today
    else:
        end = date(year, 12, 31)
    start = date(year, 1, 1)

    if start > end:
        return {"target_hours": 0.0, "actual_hours": 0.0, "overtime": 0.0}

    # Fetch holidays in range (#204: use the preloaded tenant+year set if given).
    if holidays is not None:
        holiday_dates: set = holidays
    else:
        holiday_dates = {
            h.date for h in db.query(PublicHoliday).filter(
                PublicHoliday.date >= start,
                PublicHoliday.date <= end,
                PublicHoliday.tenant_id == user.tenant_id,
            ).all()
        }

    # Fetch absences in range (exclude TRAINING, SICK, OVERTIME - same as
    # get_monthly_target). PAID_LEAVE (#145) is treated like OTHER and falls
    # through this filter, so it reduces the target like a normal absence day.
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start,
        Absence.date <= end,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    # Fix #1: half-day-aware map (full day → skip, half day → halve Soll).
    absence_half_map: Dict[date, bool] = _soll_reducing_absence_half_map(absences)

    # Fetch working hours changes (pre-loaded for the per-day loop).
    # F-027: routed through get_weekly_hours_for_date() with in-memory path.
    # #204: use the passed-in list if given (users-overview preload).
    if wh_changes is None:
        wh_changes = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user.id,
        ).order_by(WorkingHoursChange.effective_from).all()

    # #146: special-day config for the YTD year (24./31.12. always fall in
    # the same `year`, so a single lookup suffices).
    special_day_config = special_days_service.get_special_day_config(
        db, user.tenant_id, year
    )

    # Sum daily targets
    total_target = Decimal('0')
    current = start
    while current <= end:
        if (current.weekday() < 5
                and _within_employment_window(user, current)):  # #193
            # Fix #1: holiday / soll-reducing absence (full vs. half day) + #146
            # special-day factor via the shared per-day helper.
            total_target += _day_soll_contribution(
                db, user, current,
                holiday_dates=holiday_dates,
                absence_half_map=absence_half_map,
                wh_changes=wh_changes,
                special_cfg=special_day_config,
            )
        current += timedelta(days=1)

    # Sum actual hours (time entries + credited absence hours: training + sick)
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start,
        TimeEntry.date <= end,
    ).all()
    # #195: count Ist only within the employment window (symmetric to the Soll
    # loop above) — avoids phantom YTD overtime from out-of-window entries.
    total_actual = sum((Decimal(str(e.net_hours)) for e in entries
                        if _within_employment_window(user, e.date)), start=Decimal('0'))

    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start,
        Absence.date <= end,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all()
    total_actual += sum((Decimal(str(a.hours)) for a in credited_absences
                         if _within_employment_window(user, a.date)), start=Decimal('0'))

    # Include overtime carryover for this year
    carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year == year,
    ).first()
    carryover_hours = Decimal(str(carryover.overtime_hours)) if carryover else Decimal('0')

    overtime = total_actual - total_target + carryover_hours

    return {
        "target_hours": float(total_target.quantize(Decimal('0.01'))),
        "actual_hours": float(total_actual.quantize(Decimal('0.01'))),
        "overtime": float(overtime.quantize(Decimal('0.01'))),
        "carryover_hours": float(carryover_hours.quantize(Decimal('0.01'))),
    }


def half_special_day_weight(d: date, special_cfg: dict) -> Decimal:
    """#394: Tage-Kosten-Gewicht EINES Tages für die tagebasierte Urlaubs-/Absenz-
    Zählung. ``Decimal('0.5')`` wenn ``d`` als „halber Feiertag" (24./31.12.,
    ``special_day_target_factor == 0,5``) konfiguriert ist, sonst ``Decimal('1')``.

    DIE eine Quelle für alle tagebasierten Urlaubs-/Absenz-Kosten — ``get_vacation_
    account``, ``absence_days``, ``closure_split_service`` UND die Budget-Pre-Checks
    (absences/admin_vacations/vacation_requests/admin_change_requests). So kann die
    #394-Halbtags-Regel nie wieder zwischen den Buchungspfaden divergieren (der
    Re-Split + die Pre-Checks hatten den Faktor zunächst NICHT — Release-Review 1.14.3).
    ``special_cfg`` ist die je Jahr geladene ``get_special_day_config``-Map.
    """
    f = special_days_service.special_day_target_factor(d, special_cfg)
    return Decimal('0.5') if (f is not None and f == Decimal('0.5')) else Decimal('1')


def absence_days(db: Session, user: User, absences: list,
                 wh_changes: Optional[List[WorkingHoursChange]] = None) -> Decimal:
    """Zähle Abwesenheiten TAGEBASIERT (Tagesprinzip §3 BUrlG, #156/#205) — exakt
    nach derselben Regel wie ``used_days`` in ``get_vacation_account``: voller Tag
    = 1,0, ``half_day=True`` = 0,5, Legacy-Row (``half_day=None``) = Stunden ÷
    Tagessoll DES TAGES. Ein Tag mit Tagessoll 0 (Urlaub an einem Nicht-Arbeitstag)
    zählt 0. Untracked-MA (``get_daily_target<=0``, leitende Angestellte): rein
    tagebasiert (Halbtag 0,5, sonst 1,0). Quelle für die Tage-Anzeige in den
    Reports — NICHT die naive Σh ÷ Ø-Tagessoll (die für ungleichmäßige Tagespläne
    bzw. Halbtage falsch ist)."""
    tracked = get_daily_target(user) > 0
    total = Decimal('0')
    # #394: Halbtags-Sondertag (24./31.12.) → ein Absenz-Tag darauf zählt 0,5
    # (halber Arbeitstag). Config lazy je Jahr (Liste kann jahresübergreifend sein).
    _sd_cfg: dict = {}

    def _weight(d: date) -> Decimal:
        cfg = _sd_cfg.get(d.year)
        if cfg is None:
            cfg = special_days_service.get_special_day_config(db, user.tenant_id, d.year)
            _sd_cfg[d.year] = cfg
        return half_special_day_weight(d, cfg)

    for a in absences:
        if not tracked:
            base = Decimal('0.5') if a.half_day else Decimal('1')
            total += base * _weight(a.date)
            continue
        dt_day = get_daily_target_for_date(user, a.date, get_weekly_hours_for_date(db, user, a.date, wh_changes=wh_changes))
        if dt_day > 0:
            if a.half_day is None:
                total += Decimal(str(a.hours)) / Decimal(str(dt_day))
            else:
                base = Decimal('0.5') if a.half_day else Decimal('1')
                total += base * _weight(a.date)
    return total


def child_sick_cap(db: Session, user: User) -> int:
    """#376 §45 SGB V: persönlicher Kind-krank-Jahresanspruch in Tagen.
    per-MA-Feld → Tenant-Setting child_sick_days_default → 15."""
    if user.child_sick_days_per_year is not None:
        return int(user.child_sick_days_per_year)
    return settings_service.get_int_setting(db, "child_sick_days_default", user.tenant_id, 15)


def child_sick_days_used(db: Session, user: User, year: int,
                         wh_changes: Optional[List[WorkingHoursChange]] = None) -> Decimal:
    """#376: tagebasierte Summe (Tagesprinzip) der Kind-krank-Absencen im
    Kalenderjahr — nur Absencen, deren Grund tracks_child_sick_limit trägt.
    Beschäftigungsfenster wird respektiert; Zählregel identisch zu absence_days."""
    rows = (
        db.query(Absence)
        .join(AbsenceReason, Absence.reason_id == AbsenceReason.id)
        .filter(
            Absence.tenant_id == user.tenant_id,          # F-026
            Absence.user_id == user.id,
            AbsenceReason.tenant_id == user.tenant_id,     # F-026 (Join)
            AbsenceReason.tracks_child_sick_limit.is_(True),
            Absence.date >= date(year, 1, 1),
            Absence.date <= date(year, 12, 31),
        )
        .all()
    )
    windowed = [a for a in rows if _within_employment_window(user, a.date)]
    return absence_days(db, user, windowed, wh_changes=wh_changes)


def get_vacation_account(
    db: Session,
    user: User,
    year: int,
    holidays: Optional[set] = None,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Dict:
    """
    Calculate vacation account for a given year.

    #204: ``holidays`` (das tenant+year-PublicHoliday-Datumsset) und ``wh_changes``
    (die WorkingHoursChange-Liste DIESES Users) sind optionale Preloads für den
    users-overview-Hot-Loop. Default ``None`` = wie bisher pro Aufruf querien →
    byte-identische Ergebnisse (Test ``test_calc_preload``).

    Returns:
        budget_hours: Total vacation budget in hours (vacation_days × daily_target)
        budget_days: Total vacation days from user config
        used_hours: Hours of vacation taken
        used_days: Days of vacation taken (used_hours / daily_target)
        remaining_hours: Remaining vacation hours
        remaining_days: Remaining vacation days

    NOTE: Uses CURRENT weekly hours for conversion between days and hours.
    This ensures consistent display even if hours changed during the year.

    Args:
        db: Database session
        user: User object
        year: Year to calculate for

    Returns:
        Dict with vacation account details
    """
    # daily_target == 0 means the user has no Soll/Ist tracking
    # (track_hours=False, e.g. leitende Angestellte) or work_days_per_week == 0.
    # Such users still get a DAY-BASED vacation account — they are NOT shortcut
    # here. The pure day count happens further down (reine Tageszählung, hours
    # stay 0); the day-based budget below is shared with tracked users.
    # (Replaces the old F-046 "not applicable" zero shape, which made the
    # tagebasierte Budget-Check ins Leere laufen — Über-Buchung war möglich.)
    daily_target = get_daily_target(user)

    # Calculate budget in hours, pro-rated for first/last work day
    budget_days = Decimal(str(user.vacation_days))
    first_in_year = user.first_work_day and user.first_work_day.year == year
    last_in_year = user.last_work_day and user.last_work_day.year == year
    # Fix #1: a year that lies ENTIRELY outside the employment window grants no
    # budget. The pro-rata branches below only cover the entry/exit YEAR and have
    # no `else`, so without this guard a departed employee kept the full
    # `vacation_days` in every year AFTER last_work_day (and a future hire in
    # every year BEFORE first_work_day) — phantom budget that even flowed into
    # the carryover (double entitlement).
    year_outside_window = bool(
        (user.last_work_day and user.last_work_day.year < year)
        or (user.first_work_day and user.first_work_day.year > year)
    )
    if year_outside_window:
        budget_days = Decimal('0')
    elif first_in_year and last_in_year:
        # Eintritt UND Austritt im selben Jahr: Beschäftigungsdauer ist die echte
        # Überlappung beider Grenzen (nicht min() zweier einseitiger Pro-Ratas).
        # employed_months = months_remaining + months_worked − 12  (≥ 0)
        fwd = user.first_work_day
        fwd_days_in_month = monthrange(fwd.year, fwd.month)[1]
        fwd_days_remaining = fwd_days_in_month - fwd.day + 1  # inklusive Starttag
        months_remaining = (Decimal(str(12 - fwd.month))
                            + Decimal(str(fwd_days_remaining)) / Decimal(str(fwd_days_in_month)))
        lwd = user.last_work_day
        lwd_days_in_month = monthrange(lwd.year, lwd.month)[1]
        lwd_days_worked = lwd.day  # inklusive letzten Tag
        months_worked = (Decimal(str(lwd.month - 1))
                         + Decimal(str(lwd_days_worked)) / Decimal(str(lwd_days_in_month)))
        employed_months = max(Decimal('0'), months_remaining + months_worked - Decimal('12'))
        budget_days = (Decimal(str(user.vacation_days)) * employed_months / Decimal('12')).quantize(Decimal('0.1'))
    elif first_in_year:
        fwd = user.first_work_day
        days_in_month = monthrange(fwd.year, fwd.month)[1]
        days_remaining = days_in_month - fwd.day + 1  # inklusive Starttag
        # Vollständige Monate nach Startmonat + Anteil des Startmonats
        months_remaining = Decimal(str(12 - fwd.month)) + Decimal(str(days_remaining)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_remaining / Decimal('12')).quantize(Decimal('0.1'))
    elif last_in_year:
        lwd = user.last_work_day
        days_in_month = monthrange(lwd.year, lwd.month)[1]
        days_worked = lwd.day  # inklusive letzten Tag
        # Vollständige Monate vor Endmonat + Anteil des Endmonats
        months_worked = Decimal(str(lwd.month - 1)) + Decimal(str(days_worked)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_worked / Decimal('12')).quantize(Decimal('0.1'))
    # Add carryover vacation days from previous year — but only for a year the
    # employee was (at least partly) employed. An out-of-window year gets zero
    # budget and must not inherit a carryover either (Fix #1).
    if not year_outside_window:
        carryover = db.query(YearCarryover).filter(
            YearCarryover.user_id == user.id,
            YearCarryover.year == year,
        ).first()
        carryover_days = Decimal(str(carryover.vacation_days)) if carryover else Decimal('0')
        budget_days += carryover_days

    budget_hours = budget_days * daily_target

    # Calculate used vacation hours (F-033: sargable date range).
    # Only VACATION deducts the budget. PAID_LEAVE (#145) is paid leave like a
    # holiday and is intentionally NOT counted here, so a Betriebsferien booked
    # as bezahlte Freistellung leaves the vacation budget untouched.
    vacation_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.type == AbsenceType.VACATION,
        date_in_year(Absence.date, year),
    ).all()

    # #156/T2 — Tagesprinzip (§3 BUrlG, BAG): der Urlaubsverbrauch wird in
    # TAGEN gezählt, nicht als Stundensumme ÷ Durchschnitts-Tagessoll. Jeder
    # Urlaubstag zählt als Anteil seines EIGENEN Tagessolls (voller Tag = 1,0;
    # Halbtag = 0,5) — unabhängig vom Wochentag. Das verhindert, dass ein
    # Montag-Urlaub (z. B. 8h) mehr kostet als ein Dienstag-Urlaub (z. B. 3h)
    # bei ungleichmäßigem Tagesplan. Die Stundensumme bleibt nur informativ.
    # #394: config der Halbtags-Sondertage (24./31.12.) — ein Urlaubstag an einem
    # solchen Tag ist nur ein halber Arbeitstag und kostet daher 0,5 (§3 BUrlG).
    # Für alle anderen Tage bleibt der Faktor 1,0 → byte-identisch zur Altlogik.
    special_cfg_vac = special_days_service.get_special_day_config(db, user.tenant_id, year)
    used_hours = Decimal('0')
    used_days = Decimal('0')
    for a in vacation_absences:
        h = Decimal(str(a.hours))
        used_hours += h
        dt_day = get_daily_target_for_date(user, a.date, get_weekly_hours_for_date(db, user, a.date, wh_changes=wh_changes))
        # §3 BUrlG / Tagesprinzip: Urlaub an einem NICHT-Arbeitstag des MA
        # (dt_day == 0, z. B. Di/Do bei einer Mo/Mi/Fr-Kraft) verbraucht 0 Urlaubs-
        # tage — das Überspringen ist gewollt, KEIN Buchungsverlust (Funktions-
        # Review 2026-06-17 verifiziert).
        if dt_day > 0:
            if a.half_day is None:
                # #205: Legacy-Row (vor dem half_day-Feld) — tagebasierte Info
                # fehlt, daher wie bisher Stunden ÷ (live) Tagessoll. Das driftet
                # nur im seltenen Fall einer NACHTRAEGLICHEN WorkingHoursChange auf
                # ein bereits gebuchtes Datum (ohne gespeicherte Buchungszeit nicht
                # rekonstruierbar — bewusst kein unzuverlaessiges Raten).
                used_days += (h / Decimal(str(dt_day)))
            else:
                # #205: tagebasiert (Voll-Tag 1,0; Halbtag 0,5) — unabhaengig von
                # spaeteren Aenderungen des Tagessolls (kein Drift mehr).
                # #394: × 0,5 an einem Halbtags-Sondertag (zentraler Helper).
                base = Decimal('0.5') if a.half_day else Decimal('1')
                used_days += base * half_special_day_weight(a.date, special_cfg_vac)

    # #146: a special day (24./31.12.) configured as `free` + counts_as_vacation
    # consumes one vacation day too. We account for it non-invasively here
    # (no generated Absence rows): each such day is one full vacation day,
    # unless the employee already has a real VACATION absence on that day
    # (already counted above) or it falls outside their employment window.
    # Weekends / existing holidays are excluded inside the helper.
    holiday_dates_year = holidays if holidays is not None else {
        h.date for h in db.query(PublicHoliday).filter(
            date_in_year(PublicHoliday.date, year),
            PublicHoliday.tenant_id == user.tenant_id,
        ).all()
    }
    deduction_dates = special_days_service.vacation_deduction_dates_for_year(
        db, user.tenant_id, year, holiday_dates_year
    )
    existing_vacation_dates = {a.date for a in vacation_absences}

    # #189 / leitende Angestellte: a user without hours tracking
    # (daily_target == 0) gets a pure DAY count — each VACATION absence day is
    # one vacation day, each 'free'+counts_as_vacation special day (24./31.12.)
    # is one vacation day, and all hour figures stay 0. Budget (budget_days)
    # follows the normal pro-rata + carryover logic above — "sonst wie ein
    # normaler MA".
    # #205: Halbtage werden jetzt unterschieden — half_day=True zaehlt 0,5 (passt
    # zum 0,5-Vorab-Budgetcheck). Legacy-Rows (half_day=None, vor dem Feld) und
    # Voll-Tage zaehlen 1,0 wie bisher.
    if daily_target <= 0:
        # #394: halber Feiertag (24./31.12.) → 0,5 (auch für untracked/leitende).
        used_days = sum(
            ((Decimal('0.5') if a.half_day else Decimal('1'))
             * half_special_day_weight(a.date, special_cfg_vac)
             for a in vacation_absences),
            Decimal('0'),
        )
        for d in deduction_dates:
            if d in existing_vacation_dates:
                continue
            if user.first_work_day and d < user.first_work_day:
                continue
            if user.last_work_day and d > user.last_work_day:
                continue
            used_days += Decimal('1')
        return {
            "budget_hours": 0.0,
            "budget_days": float(budget_days),
            "used_hours": 0.0,
            "used_days": float(used_days.quantize(Decimal('0.1'))),
            "remaining_hours": 0.0,
            "remaining_days": float((budget_days - used_days).quantize(Decimal('0.1'))),
            "track_hours": False,  # sentinel for callers (hide hours columns)
        }

    for d in deduction_dates:
        if d in existing_vacation_dates:
            continue  # already counted via a real VACATION absence
        if user.first_work_day and d < user.first_work_day:
            continue
        if user.last_work_day and d > user.last_work_day:
            continue
        weekly_hours = get_weekly_hours_for_date(db, user, d, wh_changes=wh_changes)
        dt_day = get_daily_target_for_date(user, d, weekly_hours)
        if dt_day <= 0:
            continue
        used_hours += Decimal(str(dt_day))
        used_days += Decimal('1')  # ein freier Sondertag = 1 Urlaubstag

    # Calculate remaining — days are authoritative (Tagesprinzip); hours informativ.
    remaining_days = budget_days - used_days
    remaining_hours = budget_hours - used_hours

    return {
        "budget_hours": float(budget_hours.quantize(Decimal('0.01'))),
        "budget_days": float(budget_days),
        "used_hours": float(used_hours.quantize(Decimal('0.01'))),
        "used_days": float(used_days.quantize(Decimal('0.1'))),
        "remaining_hours": float(remaining_hours.quantize(Decimal('0.01'))),
        "remaining_days": float(remaining_days.quantize(Decimal('0.1'))),
        "track_hours": True,
    }


def count_workdays(db: Session, start: date, end: date, tenant_id=None) -> int:
    """Count weekdays (Mon-Fri) excluding public holidays between start and end (inclusive).

    F-026: pass ``tenant_id`` to scope the holiday lookup explicitly (belt-and-
    suspenders on top of RLS). When omitted the query relies on RLS alone.
    """
    years: set = set()
    cur = start
    while cur <= end:
        years.add(cur.year)
        cur += timedelta(days=1)

    holidays: set = set()
    for year in years:
        q = db.query(PublicHoliday).filter(PublicHoliday.year == year)
        if tenant_id is not None:
            q = q.filter(PublicHoliday.tenant_id == tenant_id)
        year_holidays = q.all()
        holidays.update(h.date for h in year_holidays)

    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur not in holidays:
            count += 1
        cur += timedelta(days=1)
    return count


def stale_year_closing_warning(db: Session, tenant_id, years) -> Optional[str]:
    """Fix #5: warn (non-destructively) when a retroactive change touches a year
    whose Jahresabschluss was already done.

    A year ``Y`` counts as closed when a ``YearCarryover`` for ``Y+1`` exists in
    the tenant. After a retroactive storno / closure deletion the frozen
    carryover ``Y+1`` is now stale. We deliberately do NOT recompute it (that
    could overwrite manual adjustments) — we only return a German warning string
    naming the EARLIEST affected closed year so the caller can surface it. Returns
    None when no touched year was closed.
    """
    closed = sorted({
        y for y in years
        if db.query(YearCarryover.id).filter(
            YearCarryover.tenant_id == tenant_id,
            YearCarryover.year == y + 1,
        ).first() is not None
    })
    if not closed:
        return None
    y = closed[0]
    return (
        f"Jahresabschluss {y} bereits erfolgt — Carryover {y + 1} ist nun "
        f"veraltet, bitte Jahresabschluss erneut ausführen."
    )


def create_year_closing(db: Session, year: int, users: list) -> list:
    """
    Create year-end closing for all given users.

    For each user, calculates the cumulative overtime balance at Dec 31
    and the remaining vacation days, then creates/updates a YearCarryover
    record for year+1.

    Args:
        db: Database session
        year: The year being closed (carryovers are created for year+1)
        users: List of User objects

    Returns:
        List of dicts with user info and carryover values
    """
    next_year = year + 1
    results = []

    for user in users:
        # Calculate overtime balance at end of year
        overtime_balance = get_overtime_account(db, user, year, 12)

        # Calculate remaining vacation days
        vacation_account = get_vacation_account(db, user, year)
        remaining_vacation = Decimal(str(vacation_account['remaining_days']))

        # Create or update carryover for next year (F-026: explicit tenant scope)
        carryover = db.query(YearCarryover).filter(
            YearCarryover.user_id == user.id,
            YearCarryover.tenant_id == user.tenant_id,
            YearCarryover.year == next_year,
        ).first()

        if carryover:
            carryover.overtime_hours = overtime_balance
            carryover.vacation_days = remaining_vacation
            # Fix #7: the year-closing owns this row (so delete_year_closing may
            # remove it) — even if it previously existed as a manual entry.
            carryover.source = "year_closing"
        else:
            carryover = YearCarryover(
                user_id=user.id,
                tenant_id=user.tenant_id,
                year=next_year,
                overtime_hours=overtime_balance,
                vacation_days=remaining_vacation,
                source="year_closing",  # Fix #7
            )
            db.add(carryover)

        results.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "overtime_hours": float(overtime_balance),
            "vacation_days": float(remaining_vacation.quantize(Decimal('0.1'))),
        })

    db.commit()
    return results
