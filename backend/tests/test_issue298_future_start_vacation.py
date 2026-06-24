"""#298 regression: a future-start employee must not get closure absences
(and thus "genommene Urlaubstage") for days before she starts.

Root cause: _create_closure_absences booked a VACATION/PAID_LEAVE absence for
EVERY participating employee on EVERY closure workday, ignoring first_work_day /
last_work_day. A vacation-deducting Betriebsferien (counts_as_vacation=True,
default) therefore showed a future Azubine (first_work_day in the future) with
taken vacation days today, before she had started.
"""
from datetime import date, timedelta

from app.models import User, UserRole, Absence, AbsenceType, CompanyClosure
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _mk(db, username, **kw):
    defaults = dict(
        email=f"{username}@example.com", password_hash="h", first_name="A", last_name="Z",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
        track_hours=True, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kw)
    u = User(username=username, **defaults)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _weekdays(start: date, end: date):
    out, c = [], start
    while c <= end:
        if c.weekday() < 5:
            out.append(c)
        c += timedelta(days=1)
    return out


def test_vacation_account_clean_future_start_has_zero_taken(db, default_tenant):
    """Sanity: future-start, no absences -> pro-rata budget, ZERO taken."""
    u = _mk(db, "azubi_clean", first_work_day=date(2026, 9, 1))
    vac = calculation_service.get_vacation_account(db, u, 2026)
    assert vac["used_days"] == 0.0
    assert vac["budget_days"] == 10.0  # 30 * (Sep-Dec = 4 months) / 12


def test_closure_skips_days_before_first_work_day(db, default_tenant):
    """#298: a closure spanning before + after first_work_day books absences
    ONLY on/after the employee's start — never before."""
    from app.routers.company_closures import _create_closure_absences

    admin = _mk(db, "admin298", role=UserRole.ADMIN)
    fwd = date(2026, 9, 1)  # Tuesday
    azubi = _mk(db, "azubi298", first_work_day=fwd)

    closure = CompanyClosure(
        name="Sommer/Herbst", start_date=date(2026, 8, 24), end_date=date(2026, 9, 4),
        counts_as_vacation=True, tenant_id=DEFAULT_TENANT_ID, created_by=admin.id,
    )
    db.add(closure); db.commit(); db.refresh(closure)

    workdays = _weekdays(closure.start_date, closure.end_date)
    _create_closure_absences(db, closure, workdays, [azubi], admin, delete_time_entries=True)
    db.commit()

    booked = sorted(a.date for a in db.query(Absence).filter(Absence.user_id == azubi.id).all())
    pre_start = [d for d in booked if d < fwd]
    assert pre_start == [], f"booked closure absences BEFORE first_work_day: {pre_start}"
    # the on/after-start workdays are still booked (Sep 1-4 are all weekdays)
    assert date(2026, 9, 1) in booked and date(2026, 9, 4) in booked

    # and the vacation account no longer over-counts: taken == only the in-window days
    vac = calculation_service.get_vacation_account(db, azubi, 2026)
    in_window = [d for d in workdays if d >= fwd]
    assert vac["used_days"] == float(len(in_window))


def test_closure_skips_days_after_last_work_day(db, default_tenant):
    """Mirror: a departed employee gets no closure absences after last_work_day."""
    from app.routers.company_closures import _create_closure_absences

    admin = _mk(db, "admin298b", role=UserRole.ADMIN)
    lwd = date(2026, 8, 28)  # Friday
    leaver = _mk(db, "leaver298", last_work_day=lwd)

    closure = CompanyClosure(
        name="Sommer/Herbst", start_date=date(2026, 8, 24), end_date=date(2026, 9, 4),
        counts_as_vacation=True, tenant_id=DEFAULT_TENANT_ID, created_by=admin.id,
    )
    db.add(closure); db.commit(); db.refresh(closure)

    workdays = _weekdays(closure.start_date, closure.end_date)
    _create_closure_absences(db, closure, workdays, [leaver], admin, delete_time_entries=True)
    db.commit()

    booked = sorted(a.date for a in db.query(Absence).filter(Absence.user_id == leaver.id).all())
    post_end = [d for d in booked if d > lwd]
    assert post_end == [], f"booked closure absences AFTER last_work_day: {post_end}"


def test_affected_count_excludes_out_of_window_employees(db, default_tenant):
    """#298: the affected-employee count (used by create_closure's response) must
    NOT include employees who got no absence because they are outside their window."""
    from app.routers.company_closures import _create_closure_absences

    admin = _mk(db, "admin298c", role=UserRole.ADMIN)
    in_window = _mk(db, "inwin298")  # no first_work_day -> always employed
    future = _mk(db, "fut298", first_work_day=date(2026, 9, 1))  # starts AFTER the closure

    closure = CompanyClosure(
        name="VorEintritt", start_date=date(2026, 8, 24), end_date=date(2026, 8, 28),
        counts_as_vacation=True, tenant_id=DEFAULT_TENANT_ID, created_by=admin.id,
    )
    db.add(closure); db.commit(); db.refresh(closure)

    workdays = _weekdays(closure.start_date, closure.end_date)  # all BEFORE 2026-09-01
    affected = _create_closure_absences(db, closure, workdays, [in_window, future], admin)
    db.commit()

    # only the in-window employee got absences; the future starter is skipped
    assert affected == 1, f"expected 1 affected, got {affected}"
    assert db.query(Absence).filter(Absence.user_id == future.id).count() == 0
    assert db.query(Absence).filter(Absence.user_id == in_window.id).count() == len(workdays)
