"""Audit 2026-11-07 (#539) — ArbZG-Berichte.

* A1-01: § 11 Ersatzruhetag — als „freier Tag" zählte jeder Mo–Sa-Tag ohne
  Eintrag, also auch der ohnehin freie Samstag. Zwei gearbeitete Sonntage ohne
  einen einzigen Ruhetag an einem Arbeitstag ergaben „konform".
* A1-08: Tage > 10 h, Wochen > 48 h und § 4-Pausenausnahmen waren nachträglich
  nirgends auswertbar.
* A1-13: 24-Wochen-Schnitt — Nenner Mo–Fr, Samstagsarbeit im Zähler.
* A1-14: § 6 Abs. 2 — kein Monatsdurchschnitt für Nachtarbeitnehmer.
* A2-6: Berichte ließen Ausgeschiedene und Ausgeblendete weg.
"""
from datetime import date, time, timedelta

import pytest

from app.models import Absence, AbsenceType, TimeEntry, User, UserRole
from app.models.public_holiday import PublicHoliday
from app.routers import reports
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID

TODAY = date(2026, 11, 7)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(reports, "today_local", lambda: TODAY)


def _te(db, user, d, start=time(8), end=time(16), **kw):
    db.add(TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, start_time=start,
                     end_time=end, break_minutes=kw.pop("break_minutes", 0), **kw))


def _week(db, user, monday, days=5, **kw):
    for i in range(days):
        _te(db, user, monday + timedelta(days=i), **kw)


def _row(report, user):
    return next(r for r in report["employees"] if r["user_id"] == str(user.id))


def _mk_user(db, username, **kw):
    u = User(username=username, email=f"{username}@example.com",
             password_hash=auth_service.hash_password("testpassword123"),
             first_name=kw.pop("first_name", username.title()), last_name=kw.pop("last_name", "Probe"),
             role=UserRole.EMPLOYEE, weekly_hours=kw.pop("weekly_hours", 40.0), vacation_days=30,
             work_days_per_week=kw.pop("work_days_per_week", 5), is_active=kw.pop("is_active", True),
             tenant_id=DEFAULT_TENANT_ID, **kw)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _comp(db, admin, **kw):
    return reports.get_compensatory_rest(year=2026, db=db, current_user=admin, **kw)


# --- A1-01: Ersatzruhetag ---------------------------------------------------------

def test_audit_scenario_two_sundays_without_rest_day_are_violations(db, test_user, test_admin):
    """Der Beleg aus dem Audit: So 04.10., Mo–Fr 05.–09.10., So 11.10., Mo–Fr
    12.–16.10. — kein Ruhetag an einem Arbeitstag. Der freie Samstag gleicht nichts
    aus (vorher: violations [], compliant true)."""
    _te(db, test_user, date(2026, 10, 4))
    _week(db, test_user, date(2026, 10, 5))
    _te(db, test_user, date(2026, 10, 11))
    _week(db, test_user, date(2026, 10, 12))
    _week(db, test_user, date(2026, 10, 19))  # auch danach kein Ruhetag in der Frist
    db.commit()
    row = _row(_comp(db, test_admin), test_user)
    assert row["sunday_holiday_days_worked"] == 2
    assert [v["date"] for v in row["violations"]] == ["2026-10-04", "2026-10-11"]
    assert row["violations"][0]["deadline"] == "2026-10-18"
    assert row["compliant"] is False


def test_free_workday_after_sunday_compensates(db, test_user, test_admin):
    _te(db, test_user, date(2026, 10, 4))
    _week(db, test_user, date(2026, 10, 6), days=4)  # Montag 05.10. frei
    db.commit()
    row = _row(_comp(db, test_admin), test_user)
    assert row["violations"] == []
    assert row["compensated"][0]["rest_day"] == "2026-10-05"


def test_one_rest_day_compensates_only_one_sunday(db, test_user, test_admin):
    """Ein freier Montag kann nicht zwei Sonntage ausgleichen."""
    _te(db, test_user, date(2026, 10, 4))
    _week(db, test_user, date(2026, 10, 6), days=4)   # Mo 05.10. frei
    _te(db, test_user, date(2026, 10, 11))
    _week(db, test_user, date(2026, 10, 12))
    _week(db, test_user, date(2026, 10, 19))
    db.commit()
    row = _row(_comp(db, test_admin), test_user)
    assert row["violation_count"] == 1
    assert row["violations"][0]["date"] == "2026-10-11"


def test_holiday_and_vacation_are_no_rest_days_but_other_absence_is(db, test_user, test_admin):
    _te(db, test_user, date(2026, 10, 4))
    db.add(PublicHoliday(date=date(2026, 10, 5), name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 10, 6),
                   type=AbsenceType.VACATION, hours=8))
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 10, 7),
                   type=AbsenceType.SICK, hours=8))
    _week(db, test_user, date(2026, 10, 8), days=2)
    _week(db, test_user, date(2026, 10, 12))
    db.commit()
    assert _row(_comp(db, test_admin), test_user)["violation_count"] == 1

    # Gewährter Ersatzruhetag laut Handbuch: Abwesenheit „Sonstiges"
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 10, 14),
                   type=AbsenceType.OTHER, hours=8))
    db.query(TimeEntry).filter(TimeEntry.date == date(2026, 10, 14)).delete()
    db.commit()
    row = _row(_comp(db, test_admin), test_user)
    assert row["violation_count"] == 0
    assert row["compensated"][0]["rest_day"] == "2026-10-14"


def test_future_days_do_not_compensate_and_window_stays_open(db, test_user, test_admin):
    _te(db, test_user, date(2026, 11, 1))           # Sonntag, Frist bis 15.11.
    _week(db, test_user, date(2026, 11, 2))          # Mo–Fr gearbeitet, heute = 07.11.
    db.commit()
    row = _row(_comp(db, test_admin), test_user)
    assert row["violations"] == []
    assert row["open"] == [{"date": "2026-11-01", "type": "sunday", "window_weeks": 2, "deadline": "2026-11-15"}]
    assert row["compliant"] is True


def test_actual_pattern_counts_a_usual_saturday(db, test_user, test_admin):
    """Ohne Soll am Samstag, aber regelmäßig samstags gearbeitet: ein freier
    Samstag nach dem Sonntag ist ein Ersatzruhetag (tatsächliches Muster)."""
    for sat in (date(2026, 9, 12), date(2026, 9, 19), date(2026, 9, 26), date(2026, 10, 3)):
        _te(db, test_user, sat)
    _te(db, test_user, date(2026, 10, 4))
    _week(db, test_user, date(2026, 10, 5))
    _week(db, test_user, date(2026, 10, 12))
    db.commit()
    row = _row(_comp(db, test_admin), test_user)
    assert row["violations"] == []
    assert row["compensated"][0]["rest_day"] == "2026-10-10"


def test_prior_year_sunday_consumes_january_rest_day(db, test_user, test_admin):
    """Einsätze aus dem Vorjahr verbrauchen Ruhetage mit (werden aber nicht gemeldet)."""
    _te(db, test_user, date(2025, 12, 28))  # So, Frist 11.01.
    _te(db, test_user, date(2026, 1, 4))    # So, Frist 18.01.
    _week(db, test_user, date(2025, 12, 29))  # Mo–Fr gearbeitet; Mo 05.01. frei
    for d in (date(2026, 1, 6) + timedelta(days=i) for i in range(12)):
        if d.weekday() < 5:
            _te(db, test_user, d)
    db.commit()
    row = _row(_comp(db, test_admin), test_user)
    assert row["sunday_holiday_days_worked"] == 1
    assert [v["date"] for v in row["violations"]] == ["2026-01-04"]


# --- A2-6: Auswahl der Personen ----------------------------------------------------

def test_reports_include_departed_and_hidden_on_request(db, test_admin):
    gone = _mk_user(db, "gone", is_active=False, last_work_day=date(2026, 10, 30))
    hidden = _mk_user(db, "hidden", is_hidden=True)
    for u in (gone, hidden):
        _te(db, u, date(2026, 10, 4))
        _week(db, u, date(2026, 10, 5))
        _week(db, u, date(2026, 10, 12))
    db.commit()
    rep = _comp(db, test_admin)
    ids = {r["user_id"] for r in rep["employees"]}
    assert str(gone.id) in ids and str(hidden.id) not in ids
    assert rep["hidden_with_data_count"] == 1
    rep = _comp(db, test_admin, include_hidden=True)
    assert str(hidden.id) in {r["user_id"] for r in rep["employees"]}
    assert rep["hidden_with_data_count"] == 0

    for fn, kw in (
        (reports.get_sunday_summary, {"year": 2026}),
        (reports.get_night_work_summary, {"year": 2026}),
        (reports.get_24_week_averaging_period, {"end_date": date(2026, 10, 31)}),
        (reports.get_arbzg_limits, {"year": 2026, "month": None}),
    ):
        rep = fn(db=db, current_user=test_admin, **kw)
        assert rep["hidden_with_data_count"] == 1, fn.__name__
        if fn is not reports.get_arbzg_limits:
            assert str(gone.id) in {r["user_id"] for r in rep["employees"]}, fn.__name__


def test_rest_time_report_includes_departed_employee(db, test_admin):
    gone = _mk_user(db, "gone2", is_active=False, last_work_day=date(2026, 10, 30))
    _te(db, gone, date(2026, 10, 5), time(12), time(22))
    _te(db, gone, date(2026, 10, 6), time(6), time(14))
    db.commit()
    rep = reports.get_rest_time_violations(year=2026, month=10, min_rest_hours=None, db=db, current_user=test_admin)
    assert str(gone.id) in {v["user_id"] for v in rep["violations"]}


# --- A1-13: Werktage als Nenner ----------------------------------------------------

def test_24_week_denominator_counts_saturday(db, test_user, test_admin):
    """45 h in 5 Tagen = Ø 7,5 h je Werktag (Mo–Sa), nicht 9 h."""
    test_user.first_work_day = date(2026, 10, 5)
    db.commit()
    _week(db, test_user, date(2026, 10, 5), start=time(7), end=time(16))
    db.commit()
    rep = reports.get_24_week_averaging_period(end_date=date(2026, 10, 10), db=db, current_user=test_admin)
    row = _row(rep, test_user)
    assert row["scheduled_work_days"] == 6
    assert row["average_daily_hours"] == 7.5
    assert row["compliant"] is True


def test_24_week_part_time_three_long_days(db, test_admin):
    """Teilzeit 3 × 10 h: Ø 5 h je Werktag — vorher 10 h und „Verstoß"."""
    u = _mk_user(db, "teilzeit", weekly_hours=30.0, work_days_per_week=3, first_work_day=date(2026, 10, 5))
    for d in (date(2026, 10, 5), date(2026, 10, 7), date(2026, 10, 9)):
        _te(db, u, d, start=time(7), end=time(17))
    db.commit()
    row = _row(reports.get_24_week_averaging_period(end_date=date(2026, 10, 10), db=db, current_user=test_admin), u)
    assert (row["scheduled_work_days"], row["average_daily_hours"], row["compliant"]) == (6, 5.0, True)


def test_averaging_workdays_excludes_holiday_and_vacation(test_user):
    days = reports.averaging_workdays(
        test_user, date(2026, 10, 5), date(2026, 10, 11),
        holiday_dates={date(2026, 10, 6)}, neutral_absence_dates={date(2026, 10, 7)})
    assert days == 4  # Mo, Do, Fr, Sa — So nie, Feiertag und Urlaub nicht


# --- A1-14: Nachtarbeit Monatsdurchschnitt -----------------------------------------

def test_night_worker_monthly_average(db, test_user, test_admin):
    test_user.is_night_worker = True
    test_user.first_work_day = date(2026, 9, 7)
    test_user.last_work_day = date(2026, 9, 12)
    db.commit()
    _week(db, test_user, date(2026, 9, 7), start=time(3), end=time(13))  # 5 × 10 h, je 3 h Nacht
    db.commit()
    row = _row(reports.get_night_work_summary(year=2026, db=db, current_user=test_admin), test_user)
    sept = next(m for m in row["monthly"] if m["month"] == 9)
    assert sept["workdays"] == 6
    assert sept["total_hours"] == 50.0
    assert sept["average_daily_hours"] == round(50 / 6, 2)
    assert sept["compliant"] is False
    assert row["monthly_violation_count"] == 1
    assert row["flag_missing"] is False


def test_night_worker_flag_missing_and_no_monthly_for_others(db, test_user, test_admin):
    d = date(2026, 1, 5)
    count = 0
    while count < 48:
        if d.weekday() < 5:
            _te(db, test_user, d, start=time(2), end=time(8))
            count += 1
        d += timedelta(days=1)
    other = _mk_user(db, "tagdienst")
    _te(db, other, date(2026, 1, 5))
    db.commit()
    rep = reports.get_night_work_summary(year=2026, db=db, current_user=test_admin)
    row = _row(rep, test_user)
    assert row["is_nachtarbeitnehmer"] is True and row["flag_missing"] is True
    assert row["monthly"], "Nachtarbeitnehmer laut Zählung bekommt den Monatsschnitt"
    assert _row(rep, other)["monthly"] == []


# --- A1-08: Tage > 10 h, Wochen > 48 h, Pausenausnahmen ----------------------------

def test_arbzg_limits_lists_days_weeks_and_break_exceptions(db, test_user, test_admin):
    # Mo: angerechnet 8 h (10,5 h − 150 Min. Lücke), laut Stempel 12 h → Tag > 10 h
    _te(db, test_user, date(2026, 10, 5), time(7, 45), time(18, 15), raw_start_time=time(7),
        raw_end_time=time(19), uncredited_minutes=150)
    # Di–Fr je 10 h, Sa 4 h → Woche 12 + 40 + 4 = 56 h laut Stempel
    for i in range(1, 5):
        _te(db, test_user, date(2026, 10, 5) + timedelta(days=i), time(7), time(17))
    _te(db, test_user, date(2026, 10, 10), time(8), time(12))
    # Pausenausnahme
    _te(db, test_user, date(2026, 10, 13), time(7), time(14), break_waiver_reason="Notfall, keine Pause möglich")
    db.commit()
    rep = reports.get_arbzg_limits(year=2026, month=10, db=db, current_user=test_admin)
    row = _row(rep, test_user)
    assert row["days_over_10h"] == [
        {"date": "2026-10-05", "presence_hours": 12.0, "credited_hours": 8.0, "auto_closed": False}]
    assert row["weeks_over_48h"] == [{"iso_week": "2026-W41", "presence_hours": 56.0}]
    assert row["break_exceptions"] == [{
        "date": "2026-10-13", "start_time": "07:00", "end_time": "14:00", "break_minutes": 0,
        "reason": "Notfall, keine Pause möglich"}]
    assert (rep["total_days_over_10h"], rep["total_weeks_over_48h"], rep["total_break_exceptions"]) == (1, 1, 1)

    # exakt 10 h ist kein Verstoß; andere Monate bleiben draußen
    assert reports.get_arbzg_limits(year=2026, month=9, db=db, current_user=test_admin)["employees"] == []


def test_arbzg_limits_lists_break_shortfalls_without_exception(db, test_user, test_admin):
    """Final-Review: ein § 4-Fehlbetrag ohne anerkannte Ausnahme (Ausstempeln
    mit offener/abgelehnter Beantragung, automatisch geschlossen, anerkannt)
    war im Bericht unsichtbar."""
    from app.models import ChangeRequest, ChangeRequestStatus, ChangeRequestType

    pending = TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 10, 5),
                        start_time=time(7), end_time=time(17), break_minutes=0)
    db.add(pending)
    _te(db, test_user, date(2026, 10, 6), time(8), time(15), break_minutes=0, auto_closed=True)
    _te(db, test_user, date(2026, 10, 7), time(8), time(15), break_minutes=0, credit_override=True)
    # gedeckt: 30 Min Pause bei 7 h — kein Befund
    _te(db, test_user, date(2026, 10, 8), time(8), time(15, 30), break_minutes=30)
    # anerkannte Ausnahme — steht unter break_exceptions, nicht hier
    _te(db, test_user, date(2026, 10, 9), time(8), time(15), break_waiver_reason="Notfall im Wartezimmer")
    # geteilter Dienst: Abstand 60 Min zählt als Pause — kein Befund
    _te(db, test_user, date(2026, 10, 12), time(7), time(11))
    _te(db, test_user, date(2026, 10, 12), time(12), time(16))
    db.flush()
    db.add(ChangeRequest(
        user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, request_type=ChangeRequestType.UPDATE,
        entry_kind="time_entry", status=ChangeRequestStatus.PENDING, time_entry_id=pending.id,
        proposed_date=pending.date, proposed_start_time=pending.start_time,
        proposed_end_time=pending.end_time, proposed_break_minutes=0,
        reason="Keine Pause möglich", break_waiver_reason="Keine Pause möglich"))
    db.commit()
    rep = reports.get_arbzg_limits(year=2026, month=10, db=db, current_user=test_admin)
    row = _row(rep, test_user)
    assert row["break_shortfalls"] == [
        {"date": "2026-10-05", "worked_hours": 10.0, "break_minutes": 0, "required_minutes": 45,
         "shortfall_minutes": 45, "auto_closed": False, "credit_override": False,
         "waiver_request": "pending"},
        {"date": "2026-10-06", "worked_hours": 7.0, "break_minutes": 0, "required_minutes": 30,
         "shortfall_minutes": 30, "auto_closed": True, "credit_override": False,
         "waiver_request": None},
        {"date": "2026-10-07", "worked_hours": 7.0, "break_minutes": 0, "required_minutes": 30,
         "shortfall_minutes": 30, "auto_closed": False, "credit_override": True,
         "waiver_request": None},
    ]
    assert rep["total_break_shortfalls"] == 3
    assert [b["date"] for b in row["break_exceptions"]] == ["2026-10-09"]


def test_arbzg_limits_week_crossing_month_counts_whole_week(db, test_user, test_admin):
    """Eine Woche über den Monatswechsel zählt mit ALLEN Tagen."""
    for d in (date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)):
        _te(db, test_user, d, time(7), time(17))  # 50 h
    db.commit()
    row = _row(reports.get_arbzg_limits(year=2026, month=10, db=db, current_user=test_admin), test_user)
    assert row["weeks_over_48h"] == [{"iso_week": "2026-W40", "presence_hours": 50.0}]


def test_arbzg_limits_skips_exempt_and_quiet_employees(db, test_user, test_admin):
    boss = _mk_user(db, "leitung", exempt_from_arbzg=True)
    _te(db, boss, date(2026, 10, 5), time(6), time(20))
    _te(db, test_user, date(2026, 10, 5), break_minutes=30)
    db.commit()
    assert reports.get_arbzg_limits(year=2026, month=None, db=db, current_user=test_admin)["employees"] == []


# --- Fix-Runde (Review der Lane LC) -----------------------------------------------

def test_24_week_sick_and_training_days_stay_neutral(db, test_user, test_admin):
    """Art. 16 lit. b RL 2003/88/EG: Krankheit (und Fortbildung, die nicht als
    Zeiteintrag im Zähler steht) verdünnen den Schnitt nicht. Woche 1 krank bzw.
    Fortbildung, Woche 2 Mo–Sa je 10 h: 60 h / 7 Werktage (Sa 10.10. + 6) = Ø 8,57 h
    → Verstoß. Vorher 60 h / 12 = Ø 5 h „konform"."""
    test_user.first_work_day = date(2026, 10, 5)
    db.commit()
    for i in range(5):
        db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 10, 5) + timedelta(days=i),
                       type=AbsenceType.TRAINING if i == 4 else AbsenceType.SICK, hours=8))
    _week(db, test_user, date(2026, 10, 12), days=6, start=time(7), end=time(17))
    db.commit()
    row = _row(reports.get_24_week_averaging_period(end_date=date(2026, 10, 17), db=db, current_user=test_admin), test_user)
    assert row["scheduled_work_days"] == 7
    assert row["average_daily_hours"] == round(60 / 7, 2)
    assert row["compliant"] is False


def test_24_week_overtime_compensation_stays_a_workday(db, test_user, test_admin):
    """Freizeitausgleich ist der Ausgleich selbst — er bleibt ein 0-h-Werktag."""
    test_user.first_work_day = date(2026, 10, 5)
    db.commit()
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 10, 5),
                   type=AbsenceType.OVERTIME, hours=8))
    db.commit()
    row = _row(reports.get_24_week_averaging_period(end_date=date(2026, 10, 10), db=db, current_user=test_admin), test_user)
    assert row["scheduled_work_days"] == 6


def test_night_monthly_skips_empty_and_future_months_and_judges_no_workday_as_none(db, test_user, test_admin):
    test_user.is_night_worker = True
    db.commit()
    _te(db, test_user, date(2026, 9, 8), start=time(3), end=time(11))
    db.add(PublicHoliday(date=date(2026, 10, 3), name="Tag der Deutschen Einheit", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    row = _row(reports.get_night_work_summary(year=2026, db=db, current_user=test_admin), test_user)
    # Nur September hat Arbeit; Oktober (ohne Eintrag) und Dezember (Zukunft) fehlen.
    assert [m["month"] for m in row["monthly"]] == [9]

    # Person nur am Sonntag 06.09. beschäftigt und dort im Einsatz: 0 Werktage → kein Urteil.
    sun = _mk_user(db, "sonntagsdienst", is_night_worker=True,
                   first_work_day=date(2026, 9, 6), last_work_day=date(2026, 9, 6))
    _te(db, sun, date(2026, 9, 6), start=time(2), end=time(8))
    db.commit()
    srow = _row(reports.get_night_work_summary(year=2026, db=db, current_user=test_admin), sun)
    assert srow["monthly"][0]["workdays"] == 0
    assert srow["monthly"][0]["compliant"] is None
    assert srow["monthly_violation_count"] == 0


def test_night_work_summary_logs_health_data_read(db, test_admin):
    from app.models import TimeEntryAuditLog
    before = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.action == "health_data_read").count()
    reports.get_night_work_summary(year=2026, db=db, current_user=test_admin)
    rows = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.action == "health_data_read").all()
    assert len(rows) == before + 1
    assert "Nachtarbeitsbericht 2026" in rows[-1].new_note
    assert rows[-1].tenant_id == test_admin.tenant_id


def test_unsynced_next_year_new_year_is_no_rest_day(db, test_user, test_admin):
    """So 28.12.2025 gearbeitet, Mo–Mi und Fr gearbeitet, Do 01.01.2026 frei. Ohne
    Feiertagszeilen für 2026 galt der Neujahrstag als Ersatzruhetag. Mit den
    berechneten Feiertagen ist er keiner → Verstoß (Frist 11.01.)."""
    for d in (date(2025, 12, 29), date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 2)):
        _te(db, test_user, d)
    _te(db, test_user, date(2025, 12, 28))
    _week(db, test_user, date(2026, 1, 5))
    db.add(PublicHoliday(date=date(2025, 12, 25), name="1. Weihnachtstag", year=2025, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    row = _row(reports.get_compensatory_rest(year=2025, db=db, current_user=test_admin), test_user)
    assert [v["date"] for v in row["violations"]] == ["2025-12-28"]

    # Sind die Feiertage 2026 synchronisiert (hier ohne Neujahr), gelten sie.
    db.add(PublicHoliday(date=date(2026, 4, 3), name="Karfreitag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    row = _row(reports.get_compensatory_rest(year=2025, db=db, current_user=test_admin), test_user)
    assert row["compensated"][0]["rest_day"] == "2026-01-01"
