"""#314 follow-up: re-classify Betriebsferien absences into VACATION/OVERTIME.

Extracted from ``company_closures.py`` (Fix #3) so the private-vacation write
paths (``absences``, ``admin_vacations``, ``vacation_requests``) can trigger a
re-split WITHOUT importing the router — which would risk a circular import.
``company_closures`` re-imports ``resplit_year_closures`` as
``_resplit_year_closures`` so its existing call sites keep working.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.models import User, Absence, AbsenceType, PublicHoliday, CompanyClosure
from app.services import calculation_service, settings_service, special_days_service


def resplit_year_closures(db: Session, tenant_id, year: int, current_user: User = None) -> None:
    """#314 follow-up: re-classify ALL split-able Betriebsferien absences of a
    year into VACATION/OVERTIME in CALENDAR order.

    ``_create_closure_absences`` decides VACATION-vs-OVERTIME per closure at save
    time against the then-current remaining budget. Entering the December closure
    BEFORE the (calendar-earlier) June closure therefore let December "inherit"
    the vacation budget and pushed June onto OVERTIME — the booking followed the
    INPUT order, not the calendar. This second pass fixes that surgically: it
    walks ALL of the year's closure days in DATE order against the gross annual
    budget minus all non-closure vacation consumption (private vacation + free
    special days) and flips only ``absence.type``. The surplus over the budget
    thus lands on the LAST closure of the year (never minus-vacation; once the
    budget is exhausted the walk switches to OVERTIME).

    Only ``absence.type`` of existing closure absences is mutated — no day is
    created or deleted, so every guard in ``_create_closure_absences`` (#298
    employment window, off-day skip, AC-11 free special days, #290 logged-work,
    foreign-absence skip, audit log, half_day, closure_id, hours) stays intact.

    Runs only when the global ``closure_overtime_after_vacation`` toggle is on
    (otherwise legacy all-VACATION). Untracked employees (track_hours=False) have
    no overtime account and are left as VACATION (mirrors the emp_split guard).
    F-026: every query is tenant-scoped. ``current_user`` is accepted for call-
    site compatibility but unused (everything keys off ``tenant_id``).
    """
    if not settings_service.get_bool_setting(
        db, "closure_overtime_after_vacation", tenant_id, False
    ):
        return

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    # Split-able closures = vacation closures of this tenant that touch the year.
    closures = db.query(CompanyClosure).filter(
        CompanyClosure.tenant_id == tenant_id,
        CompanyClosure.counts_as_vacation == True,
        CompanyClosure.start_date <= year_end,
        CompanyClosure.end_date >= year_start,
    ).all()
    if not closures:
        return
    closure_ids = [c.id for c in closures]

    # All generated absences of those closures that fall in this year.
    closure_absences = db.query(Absence).filter(
        Absence.tenant_id == tenant_id,
        Absence.closure_id.in_(closure_ids),
        Absence.date >= year_start,
        Absence.date <= year_end,
    ).all()
    if not closure_absences:
        return

    by_user: dict = {}
    for a in closure_absences:
        by_user.setdefault(a.user_id, []).append(a)

    users = {
        u.id: u
        for u in db.query(User).filter(
            User.id.in_(list(by_user.keys())),
            User.tenant_id == tenant_id,
        ).all()
    }

    # Free special days (24./31.12.) that cost a vacation day this year — same
    # source get_vacation_account uses, so the budget bookkeeping matches.
    holiday_dates_year = {
        h.date
        for h in db.query(PublicHoliday).filter(
            PublicHoliday.year == year,
            PublicHoliday.tenant_id == tenant_id,
        ).all()
    }
    deduction_dates = special_days_service.vacation_deduction_dates_for_year(
        db, tenant_id, year, holiday_dates_year
    )

    for user_id, absences in by_user.items():
        employee = users.get(user_id)
        # Untracked MA: no overtime account → keep legacy VACATION. Missing user
        # (shouldn't happen) → leave untouched.
        if employee is None or not employee.track_hours:
            continue

        # Gross annual budget (pro-rata + carryover), independent of bookings.
        budget = float(
            calculation_service.get_vacation_account(db, employee, year)["budget_days"]
        )

        # Non-closure vacation consumption (private vacation + free special days)
        # is ALL deducted up front, so the closure days only ever take the
        # REMAINING budget — even vacation booked LATER in the year (e.g. summer)
        # reduces the closure budget (#314 reopened: NIE Minus-Urlaub).
        private = db.query(Absence).filter(
            Absence.user_id == user_id,
            Absence.tenant_id == tenant_id,
            Absence.type == AbsenceType.VACATION,
            Absence.closure_id.is_(None),
            Absence.date >= year_start,
            Absence.date <= year_end,
        ).all()
        private_dates = {a.date for a in private}
        consumed = 0.0
        for a in private:
            # Fix #3: skip days with Tagessoll 0 (e.g. a use_daily_schedule MA's
            # free weekday) exactly like get_vacation_account's used_days loop —
            # a vacation day on a non-working day consumes 0 budget. Without this
            # ``consumed`` overcounted → closure_budget too small → a closure day
            # wrongly fell to OVERTIME.
            dt_day = calculation_service.get_daily_target_for_date(
                employee, a.date,
                weekly_hours=calculation_service.get_weekly_hours_for_date(db, employee, a.date),
            )
            if dt_day <= 0:
                continue
            consumed += 0.5 if a.half_day else 1.0
        for d in deduction_dates:
            if d in private_dates:
                continue  # already counted via a real VACATION absence
            if employee.first_work_day and d < employee.first_work_day:
                continue
            if employee.last_work_day and d > employee.last_work_day:
                continue
            # Fix #3: same Tagessoll>0 guard get_vacation_account applies to free
            # special days (24./31.12.) — a free day on the MA's non-working
            # weekday costs no vacation, so it must not reduce closure_budget.
            dt_day = calculation_service.get_daily_target_for_date(
                employee, d,
                weekly_hours=calculation_service.get_weekly_hours_for_date(db, employee, d),
            )
            if dt_day <= 0:
                continue
            consumed += 1.0

        closure_budget = budget - consumed

        # Walk the closure days in CALENDAR order: VACATION while the remaining
        # closure budget covers a full day, OVERTIME afterwards. The surplus
        # therefore lands on the latest closure of the year.
        used = 0.0
        for a in sorted(absences, key=lambda x: x.date):
            if closure_budget - used >= 1.0:
                a.type = AbsenceType.VACATION
                used += 1.0
            else:
                a.type = AbsenceType.OVERTIME
