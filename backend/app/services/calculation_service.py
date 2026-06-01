from datetime import date, datetime, timedelta
from app.services.timezone_service import today_local
from app.services.date_filters import date_in_year, date_in_month
from decimal import Decimal
from calendar import monthrange
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType, WorkingHoursChange, YearCarryover
from app.services import special_days_service


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


def get_monthly_target(db: Session, user: User, year: int, month: int) -> Decimal:
    """
    Calculate monthly target hours.

    Formula:
    For each weekday (Mon-Fri) in month:
        - Skip public holidays
        - Skip absence days
        - Add daily target (based on weekly hours valid for that date)

    IMPORTANT: Absences REDUCE the target, because the employee
    doesn't need to work on those days.

    This function now considers historical working hours changes,
    so if hours changed mid-month, both values are used correctly.

    Args:
        db: Database session
        user: User object
        year: Year
        month: Month (1-12)

    Returns:
        Monthly target hours as Decimal (0 if track_hours is False)
    """
    if not user.track_hours:
        return Decimal('0')

    # Get holidays and absences for the month (F-033: sargable date range)
    holidays = db.query(PublicHoliday).filter(
        date_in_month(PublicHoliday.date, year, month),
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()
    holiday_dates = {h.date for h in holidays}

    # Exclude TRAINING, SICK, and OVERTIME from target reduction:
    # - TRAINING counts as worked time (außer Haus)
    # - SICK: §3 EntgFG - employee must be credited as if they worked the planned hours
    # - OVERTIME: Überstundenausgleich – Soll bleibt bestehen, Tag zählt als 0h Ist,
    #   dadurch reduziert sich das Überstundenkonto um die geplanten Stunden
    # VACATION, OTHER and PAID_LEAVE (#145) are NOT excluded -> they all
    # reduce the target (the employee doesn't have to work those days). For
    # PAID_LEAVE the rechen-mechanik is identical to OTHER; the difference is
    # only that PAID_LEAVE is paid and doesn't touch the vacation budget
    # (see get_vacation_account, which sums only VACATION).
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        date_in_month(Absence.date, year, month),
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    absence_dates = {a.date for a in absences}

    # #146: configurable handling of 24./31.12. (working_day | half_day | free).
    # Loaded once per call; applied per day below.
    special_day_config = special_days_service.get_special_day_config(
        db, user.tenant_id, year
    )

    # Calculate target by iterating through each day
    _, last_day = monthrange(year, month)
    monthly_target = Decimal('0')

    for day in range(1, last_day + 1):
        d = date(year, month, day)

        # Skip weekends
        if d.weekday() >= 5:  # Saturday or Sunday
            continue

        # #193: skip days outside the employment window (before entry / after exit)
        if not _within_employment_window(user, d):
            continue

        # Skip holidays and absences
        if d in holiday_dates or d in absence_dates:
            continue

        # Get weekly hours valid for this specific date
        weekly_hours = get_weekly_hours_for_date(db, user, d)
        daily_target = get_daily_target_for_date(user, d, weekly_hours)

        # #146: apply the special-day rule (after weekend/holiday/absence so we
        # never double-handle a 24./31.12. that already is a weekend or holiday).
        factor = special_days_service.special_day_target_factor(d, special_day_config)
        if factor is not None:
            daily_target = (daily_target * factor)

        monthly_target += daily_target

    return monthly_target.quantize(Decimal('0.01'))


def get_monthly_actual(db: Session, user: User, year: int, month: int) -> Decimal:
    """
    Calculate actual hours worked in a month.
    Sum of all net_hours from TimeEntry records + credited absence hours.

    Training (Fortbildung) and sick-leave (Kranktage) hours count as worked time:
    - Training: employee is absent but credited for the planned hours.
    - Sick: §3 EntgFG – employee must be credited as if they worked the planned hours.

    Args:
        db: Database session
        user: User object
        year: Year
        month: Month (1-12)

    Returns:
        Actual hours worked as Decimal
    """
    # F-033: sargable date range. The Python-level Decimal sum is kept
    # because the SQL @expression for net_hours relies on Postgres's
    # EXTRACT(EPOCH FROM time - time) semantics which do not port to
    # SQLite used by the test suite. Fetching the rows is still faster
    # than per-day queries thanks to the composite index from Sprint 3.1.
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        date_in_month(TimeEntry.date, year, month),
    ).all()
    total = sum((entry.net_hours for entry in entries), start=Decimal('0'))

    # Training and sick hours count as actual worked hours:
    # - TRAINING: außer Haus, credited as worked
    # - SICK: §3 EntgFG - credited as if the planned hours were worked
    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
        date_in_month(Absence.date, year, month),
    ).all()
    credited_hours = sum((Decimal(str(a.hours)) for a in credited_absences), Decimal('0'))

    return (Decimal(str(total)) + credited_hours).quantize(Decimal('0.01'))


def get_monthly_balance(db: Session, user: User, year: int, month: int) -> Decimal:
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
    target = get_monthly_target(db, user, year, month)
    actual = get_monthly_actual(db, user, year, month)

    balance = actual - target

    return balance.quantize(Decimal('0.01'))


def get_overtime_account(db: Session, user: User, up_to_year: int, up_to_month: int) -> Decimal:
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
    actual_by_month: Dict[tuple, Decimal] = {}
    for e in entries:
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
    absence_dates: set[date] = {a.date for a in absences}

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
            # #193: skip days outside the employment window (before entry / after exit)
            if not _within_employment_window(user, d):
                continue
            if d in holiday_dates or d in absence_dates:
                continue
            weekly_hours = get_weekly_hours_for_date(db, user, d, wh_changes=wh_changes)
            daily_target = get_daily_target_for_date(user, d, weekly_hours)
            # #146: apply special-day rule (half_day → ×0.5, free → ×0).
            factor = special_days_service.special_day_target_factor(d, cfg)
            if factor is not None:
                daily_target = (daily_target * factor)
            monthly_target += daily_target

        monthly_actual = actual_by_month.get(key, Decimal('0'))
        total_balance += (monthly_actual - monthly_target)

        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1

    return total_balance.quantize(Decimal('0.01'))


def get_ytd_summary(db: Session, user: User, year: int = None) -> Dict:
    """
    Calculate year-to-date summary from Jan 1 to today.

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

    # End date: today if current year, else Dec 31
    end = today if year == today.year else date(year, 12, 31)
    start = date(year, 1, 1)

    if start > end:
        return {"target_hours": 0.0, "actual_hours": 0.0, "overtime": 0.0}

    # Fetch holidays in range
    holidays = db.query(PublicHoliday).filter(
        PublicHoliday.date >= start,
        PublicHoliday.date <= end,
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()
    holiday_dates: set = {h.date for h in holidays}

    # Fetch absences in range (exclude TRAINING, SICK, OVERTIME - same as
    # get_monthly_target). PAID_LEAVE (#145) is treated like OTHER and falls
    # through this filter, so it reduces the target like a normal absence day.
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start,
        Absence.date <= end,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    absence_dates: set = {a.date for a in absences}

    # Fetch working hours changes (pre-loaded for the per-day loop).
    # F-027: routed through get_weekly_hours_for_date() with in-memory path
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
        if (current.weekday() < 5 and current not in holiday_dates
                and current not in absence_dates
                and _within_employment_window(user, current)):  # #193
            weekly_hours = get_weekly_hours_for_date(db, user, current, wh_changes=wh_changes)
            daily_target = get_daily_target_for_date(user, current, weekly_hours)
            # #146: apply special-day rule (half_day → ×0.5, free → ×0).
            factor = special_days_service.special_day_target_factor(current, special_day_config)
            if factor is not None:
                daily_target = (daily_target * factor)
            total_target += daily_target
        current += timedelta(days=1)

    # Sum actual hours (time entries + credited absence hours: training + sick)
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start,
        TimeEntry.date <= end,
    ).all()
    total_actual = sum((Decimal(str(e.net_hours)) for e in entries), start=Decimal('0'))

    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start,
        Absence.date <= end,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all()
    total_actual += sum((Decimal(str(a.hours)) for a in credited_absences), start=Decimal('0'))

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


def get_vacation_account(db: Session, user: User, year: int) -> Dict:
    """
    Calculate vacation account for a given year.

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
    if user.first_work_day and user.first_work_day.year == year:
        fwd = user.first_work_day
        days_in_month = monthrange(fwd.year, fwd.month)[1]
        days_remaining = days_in_month - fwd.day + 1  # inklusive Starttag
        # Vollständige Monate nach Startmonat + Anteil des Startmonats
        months_remaining = Decimal(str(12 - fwd.month)) + Decimal(str(days_remaining)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_remaining / Decimal('12')).quantize(Decimal('0.1'))
    if user.last_work_day and user.last_work_day.year == year:
        lwd = user.last_work_day
        days_in_month = monthrange(lwd.year, lwd.month)[1]
        days_worked = lwd.day  # inklusive letzten Tag
        # Vollständige Monate vor Endmonat + Anteil des Endmonats
        months_worked = Decimal(str(lwd.month - 1)) + Decimal(str(days_worked)) / Decimal(str(days_in_month))
        budget_days_last = (Decimal(str(user.vacation_days)) * months_worked / Decimal('12')).quantize(Decimal('0.1'))
        budget_days = min(budget_days, budget_days_last)
    # Add carryover vacation days from previous year
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
    used_hours = Decimal('0')
    used_days = Decimal('0')
    for a in vacation_absences:
        h = Decimal(str(a.hours))
        used_hours += h
        dt_day = get_daily_target_for_date(user, a.date, get_weekly_hours_for_date(db, user, a.date))
        if dt_day > 0:
            used_days += (h / Decimal(str(dt_day)))

    # #146: a special day (24./31.12.) configured as `free` + counts_as_vacation
    # consumes one vacation day too. We account for it non-invasively here
    # (no generated Absence rows): each such day is one full vacation day,
    # unless the employee already has a real VACATION absence on that day
    # (already counted above) or it falls outside their employment window.
    # Weekends / existing holidays are excluded inside the helper.
    holiday_dates_year = {
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
    # is one vacation day, and all hour figures stay 0. Half days are not
    # distinguishable without hours (Absence has no half_day flag, hours=0) and
    # therefore count as a full day. Budget (budget_days) follows the normal
    # pro-rata + carryover logic above — "sonst wie ein normaler MA".
    if daily_target <= 0:
        used_days = Decimal(str(len(vacation_absences)))
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
        weekly_hours = get_weekly_hours_for_date(db, user, d)
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

        # Create or update carryover for next year
        carryover = db.query(YearCarryover).filter(
            YearCarryover.user_id == user.id,
            YearCarryover.year == next_year,
        ).first()

        if carryover:
            carryover.overtime_hours = overtime_balance
            carryover.vacation_days = remaining_vacation
        else:
            carryover = YearCarryover(
                user_id=user.id,
                tenant_id=user.tenant_id,
                year=next_year,
                overtime_hours=overtime_balance,
                vacation_days=remaining_vacation,
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
