"""#204 Item 1: die optionalen Preload-Parameter (holidays=/wh_changes=) an
get_vacation_account / get_ytd_summary / absence_days / child_sick_days_used
müssen BYTE-IDENTISCHE Ergebnisse liefern wie der re-querying-Default-Pfad.
Sonst wäre der Perf-Refactor eine (verbotene) Änderung am auditierten Calc.
"""
from datetime import date, time
from decimal import Decimal

from app.models import User, TimeEntry, Absence, AbsenceType, PublicHoliday, WorkingHoursChange, AbsenceReason
from app.services import calculation_service as calc
from app.services.date_filters import date_in_year
from tests.conftest import DEFAULT_TENANT_ID


def _seed(db):
    """Nicht-trivialer Datensatz: WHChange mitten im Jahr, Urlaub nach der
    Änderung, Feiertage im Zeitraum, Zeiteinträge vor/nach der Änderung."""
    u = User(username="pl", email="pl@x.de", password_hash="x", first_name="P",
             last_name="L", role="employee", weekly_hours=Decimal("40"),
             vacation_days=30, work_days_per_week=5, is_active=True,
             tenant_id=DEFAULT_TENANT_ID)
    db.add(u); db.commit(); db.refresh(u)
    # Wochenstunden 40 → ab 01.04. auf 20.
    db.add(WorkingHoursChange(user_id=u.id, tenant_id=DEFAULT_TENANT_ID,
                              effective_from=date(2026, 4, 1), weekly_hours=Decimal("20")))
    # Urlaub am Mo 11.05. (nach der Änderung → Tagessoll aus weekly=20).
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 5, 11),
                   type=AbsenceType.VACATION, hours=Decimal("4"), half_day=False))
    # Feiertage im Zeitraum.
    db.add(PublicHoliday(date=date(2026, 1, 1), name="Neujahr", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.add(PublicHoliday(date=date(2026, 5, 1), name="Tag der Arbeit", year=2026, tenant_id=DEFAULT_TENANT_ID))
    # Zeiteinträge vor/nach der Änderung (für YTD-Ist).
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 2, 2),
                     start_time=time(8, 0), end_time=time(16, 0), break_minutes=0))
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 5, 5),
                     start_time=time(9, 0), end_time=time(13, 0), break_minutes=0))
    db.commit(); db.refresh(u)
    return u


def _preloads(db, user, year):
    holidays = {h.date for h in db.query(PublicHoliday).filter(
        PublicHoliday.tenant_id == user.tenant_id,
        date_in_year(PublicHoliday.date, year),
    ).all()}
    wh = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.tenant_id == user.tenant_id,
        WorkingHoursChange.user_id == user.id,
    ).order_by(WorkingHoursChange.effective_from).all()
    return holidays, wh


def test_get_vacation_account_preload_byte_identical(db, default_tenant):
    u = _seed(db)
    holidays, wh = _preloads(db, u, 2026)
    plain = calc.get_vacation_account(db, u, 2026)
    pre = calc.get_vacation_account(db, u, 2026, holidays=holidays, wh_changes=wh)
    assert plain == pre


def test_get_ytd_summary_preload_byte_identical(db, default_tenant):
    u = _seed(db)
    holidays, wh = _preloads(db, u, 2026)
    cutoff = date(2026, 6, 30)  # Range Jan–Jun umspannt die WHChange (01.04.)
    plain = calc.get_ytd_summary(db, u, 2026, cutoff_date=cutoff)
    pre = calc.get_ytd_summary(db, u, 2026, cutoff_date=cutoff, holidays=holidays, wh_changes=wh)
    assert plain == pre


def test_absence_days_preload_byte_identical(db, default_tenant):
    u = _seed(db)
    _, wh = _preloads(db, u, 2026)
    absences = db.query(Absence).filter(Absence.user_id == u.id).all()
    assert calc.absence_days(db, u, absences) == calc.absence_days(db, u, absences, wh_changes=wh)


def test_child_sick_days_used_preload_byte_identical(db, default_tenant):
    u = _seed(db)
    # Kind-krank-Grund + eine Absence darauf.
    r = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Kind krank", color="#f00",
                      base_behavior="unpaid_free", tracks_child_sick_limit=True, is_active=True)
    db.add(r); db.commit(); db.refresh(r)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 5, 12),
                   type=AbsenceType.OTHER, hours=Decimal("4"), half_day=False, reason_id=r.id))
    db.commit()
    _, wh = _preloads(db, u, 2026)
    assert calc.child_sick_days_used(db, u, 2026) == calc.child_sick_days_used(db, u, 2026, wh_changes=wh)


def test_users_overview_matches_per_user_compute(db, default_tenant):
    """#204 Integration: der Endpoint mit Preload liefert je User EXAKT die
    per-User-berechneten Zahlen — beweist, dass die WHChange-Gruppierung dem
    richtigen User zugeordnet wird (kein Grouping-Bug)."""
    from app.routers.admin_users import users_overview
    admin = User(username="adm", email="adm@x.de", password_hash="x", first_name="A",
                 last_name="D", role="admin", weekly_hours=Decimal("40"), vacation_days=30,
                 work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(admin); db.commit(); db.refresh(admin)
    u1 = _seed(db)  # weekly 40 → ab 01.04. 20, Urlaub 11.05.
    # u2: anderer Verlauf (weekly 30 → ab 01.06. 10, Urlaub 20.02. VOR der Änderung).
    u2 = User(username="u2", email="u2@x.de", password_hash="x", first_name="U",
              last_name="2", role="employee", weekly_hours=Decimal("30"), vacation_days=25,
              work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(u2); db.commit(); db.refresh(u2)
    db.add(WorkingHoursChange(user_id=u2.id, tenant_id=DEFAULT_TENANT_ID,
                              effective_from=date(2026, 6, 1), weekly_hours=Decimal("10")))
    db.add(Absence(user_id=u2.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 2, 20),
                   type=AbsenceType.VACATION, hours=Decimal("6"), half_day=False))
    db.commit()

    rows = users_overview(db=db, current_user=admin, year=2026)
    by_id = {r.user_id: r for r in rows}
    for u in (u1, u2):
        expected = calc.get_vacation_account(db, u, 2026)  # Default-Pfad, kein Preload
        row = by_id[str(u.id)]
        assert row.vacation.remaining_days == expected["remaining_days"]
        assert row.vacation.used_days == expected["used_days"]


def test_users_overview_preload_constant_query_count(db, default_tenant):
    """#204: die Feiertags- und WorkingHoursChange-Queries sind KONSTANT (je 1
    Preload) — unabhängig von der User-Zahl. Der eigentliche N+1-Beweis."""
    from sqlalchemy import event
    from app.routers.admin_users import users_overview
    from tests.conftest import engine
    admin = User(username="adm", email="adm@x.de", password_hash="x", first_name="A",
                 last_name="D", role="admin", weekly_hours=Decimal("40"), vacation_days=30,
                 work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(admin); db.commit(); db.refresh(admin)
    db.add(PublicHoliday(date=date(2026, 1, 1), name="Neujahr", year=2026, tenant_id=DEFAULT_TENANT_ID))
    for i in range(5):
        u = User(username=f"e{i}", email=f"e{i}@x.de", password_hash="x", first_name="E",
                 last_name=str(i), role="employee", weekly_hours=Decimal("40"), vacation_days=30,
                 work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
        db.add(u); db.commit(); db.refresh(u)
        db.add(WorkingHoursChange(user_id=u.id, tenant_id=DEFAULT_TENANT_ID,
                                  effective_from=date(2026, 4, 1), weekly_hours=Decimal("20")))
    db.commit()

    counts = {"holidays": 0, "wh": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        s = statement.lower()
        if "from public_holidays" in s:
            counts["holidays"] += 1
        if "from working_hours_changes" in s:
            counts["wh"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        rows = users_overview(db=db, current_user=admin, year=2026)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    assert len(rows) == 6  # admin + 5
    assert counts["holidays"] == 1, counts  # 1 Preload statt 6×
    assert counts["wh"] == 1, counts        # 1 Preload statt 6×
