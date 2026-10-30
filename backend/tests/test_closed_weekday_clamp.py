"""Werktag ohne Arbeitszeit-Blöcke im Blockmodell: nichts wird angerechnet.

Kundenfall 2026-10-30: MA arbeitet künftig Di 07:30–13:00 und Do 15:00–18:00.
Stempelt sie an einem Montag, darf die Zeit nur nach Anerkennung zählen — bis
1.20.3 wurde ein Werktag ohne Blöcke gar nicht gekappt und voll angerechnet.

Ausgenommen bleiben Wochenende, Feiertage und freie Sondertage (#484, §10 ArbZG),
Altfenster aus Migration 073 (dort hieß „Tag ohne Fenster" schon immer „keine
Kappung"), Personen ohne Blöcke, ``track_hours=False`` und anerkannte Einträge.
"""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import TimeEntry, User, UserRole
from app.models.public_holiday import PublicHoliday
from app.services import work_blocks_service, work_window_service as wws
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import add_row, entry, t
from tests.work_blocks_fixtures import MON, block_week, legacy_week

TUE = date(2026, 6, 2)
SAT = date(2026, 6, 6)
EASTER_MONDAY = date(2026, 4, 6)
CUSTOMER_WEEK = block_week(tue=[("07:30", "13:00")], thu=[("15:00", "18:00")])
CLOSED_TEXT = (
    "An diesem Tag sind keine Arbeitszeit-Blöcke hinterlegt — angerechnet werden 0 Stunden. "
    "Die gestempelte Zeit bleibt gespeichert."
)


def _user(blocks=CUSTOMER_WEEK, track_hours=True):
    return User(
        username="closed_day", email="closed@x.de", password_hash="h", first_name="C", last_name="D",
        role=UserRole.EMPLOYEE, weekly_hours=8.5, work_days_per_week=2, vacation_days=30,
        track_hours=track_hours, tenant_id=DEFAULT_TENANT_ID, work_blocks=blocks,
    )


def _net(r, brk=0):
    e = TimeEntry(start_time=r.eff_start, end_time=r.eff_end, raw_start_time=r.raw_start,
                  raw_end_time=r.raw_end, break_minutes=brk, uncredited_minutes=r.uncredited_minutes)
    return e.net_hours, wws.not_credited_minutes(e)


@pytest.fixture
def easter(db, default_tenant):
    db.add(PublicHoliday(date=EASTER_MONDAY, name="Ostermontag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


def test_closed_weekday_collapses_to_zero(db, default_tenant):
    r = wws.clamp(db, _user(), MON, time(8), time(12), 15, credit_override=False)
    assert r == wws.ClampResult(time(8), time(8), time(8), time(12), 0, 15)
    assert _net(r) == (Decimal("0.00"), 240)


def test_closed_weekday_open_entry_keeps_start_and_carries_grace(db, default_tenant):
    r = wws.clamp(db, _user(), MON, time(8), None, 15, credit_override=False)
    assert r == wws.ClampResult(time(8), None, None, None, 0, 15)


def test_closed_weekday_text_with_employee_hint(db, default_tenant):
    user = _user()
    closed = wws.clamp(db, user, MON, time(8), time(12), 15, credit_override=False)
    assert wws.clamp_warning_text(db, user, MON, closed, for_employee=False) == CLOSED_TEXT
    assert wws.clamp_warning_text(db, user, MON, closed, for_employee=True) == (
        CLOSED_TEXT + wws.EMPLOYEE_CREDIT_HINT)
    clock_in = wws.clamp(db, user, MON, time(8), None, 15, credit_override=False)
    assert wws.clamp_warning_text(db, user, MON, clock_in, for_employee=False) == CLOSED_TEXT


def test_block_day_is_clamped_as_before(db, default_tenant):
    r = wws.clamp(db, _user(), TUE, time(7), time(14), 15, credit_override=False)
    assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == (time(7, 15), time(13, 15), time(7), time(14))


@pytest.mark.parametrize("kwargs", [
    dict(blocks=legacy_week(tue=("07:30", "13:00"))),   # Altfenster aus 073
    dict(blocks=None),                                   # keine Blöcke
    dict(track_hours=False),
])
def test_exempt_people_are_not_clamped_on_free_weekday(db, default_tenant, kwargs):
    r = wws.clamp(db, _user(**kwargs), MON, time(8), time(12), 15, credit_override=False)
    assert r == wws.ClampResult(time(8), time(12), None, None, 0, None)


def test_credit_override_is_not_clamped(db, default_tenant):
    r = wws.clamp(db, _user(), MON, time(8), time(12), 15, credit_override=True)
    assert r == wws.ClampResult(time(8), time(12), None, None, 0, None)


def test_weekend_and_holiday_stay_unclamped(db, easter):
    user = _user()
    for d in (SAT, EASTER_MONDAY):
        r = wws.clamp(db, user, d, time(8), time(12), 15, credit_override=False)
        assert r == wws.ClampResult(time(8), time(12), None, None, 0, None), d


def test_clamp_applies_on_closed_weekday(db, default_tenant):
    assert wws.clamp_applies(db, _user(), MON, credit_override=False) is True
    assert wws.clamp_applies(db, _user(blocks=legacy_week(tue=("07:30", "13:00"))), MON,
                             credit_override=False) is False


def test_credit_blocks_distinguishes_unclamped_from_closed(db, easter):
    user = _user()
    assert wws.credit_blocks(db, user, MON) == []
    assert wws.credit_blocks(db, user, TUE) == [(450, 780)]
    assert wws.credit_blocks(db, user, SAT) is None
    assert wws.credit_blocks(db, user, EASTER_MONDAY) is None
    assert wws.credit_blocks(db, _user(blocks=None), MON) is None


def test_credited_minutes_for_closed_day_is_zero():
    assert wws.credited_minutes_for([], 15, 480, 720) == 0
    assert wws.credited_minutes_for(None, 15, 480, 720) == 240


def test_open_entry_loses_when_its_day_closes():
    assert wws.open_entry_loses([(480, 720)], [], 15, time(8), time(10)) is True
    assert wws.open_entry_loses(None, [], 15, time(8), time(10)) is True
    assert wws.open_entry_loses(None, None, 15, time(8), time(10)) is False


def test_reclamp_closes_a_former_block_day(db, test_user):
    old = block_week(mon=[("07:30", "13:00"), ("15:00", "18:00")])
    add_row(db, test_user, date(2026, 1, 1), week=old)
    add_row(db, test_user, MON, week=CUSTOMER_WEEK)
    e = entry(db, test_user, MON, t(7, 15), t(12))  # auf der alten Hüllenkante
    prev = work_blocks_service.parse_week_blocks(old).blocks
    result = wws.reclamp_time_entries(db, test_user, MON, date(2026, 6, 30), {0, 1, 3}, prev, 15)
    [c] = result.changed
    assert (c.old_net, c.new_net) == (Decimal("4.75"), Decimal("0.00"))
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time) == (t(7, 15), t(7, 15), t(7, 15), t(12))
    assert result.flagged == []


# Release-Review 1.21 (Fund 0): ein leerer Wochentag wechselt seine Bedeutung,
# wenn ein Snapshot ohne Blöcke (oder eine Altzeile) von einer Woche im
# Blockmodell abgelöst wird — und umgekehrt. Die Neukappung muss diese Tage
# mitnehmen, sonst behalten Einträge dort still ihre volle Anrechnung.
from app.services import wh_change_service  # noqa: E402
from tests.wh_change_helpers import change_row, freeze  # noqa: E402

FRI_IN_WINDOW = date(2026, 10, 2)    # Freitag zwischen EFF (01.09.) und TODAY (08.10.)
MON_THU = block_week(mon=[("08:00", "12:00")], tue=[("08:00", "12:00")],
                     wed=[("08:00", "12:00")], thu=[("08:00", "12:00")])


def _run_change(db, user, admin, week, eff=date(2026, 9, 1)):
    return wh_change_service.run_change(db, user, admin_id=admin.id, effective_from=eff,
                                        apply=lambda: db.add(change_row(user, eff, week=week)))


@pytest.mark.parametrize("old", [
    dict(weekly_hours=20),                                              # ohne Blöcke
    dict(weekly_hours=20, blocks=legacy_week(mon=("07:00", "17:00"))),  # Altfenster, Fr leer
])
def test_weekday_turning_blockless_is_reclamped(db, test_user, test_admin, monkeypatch, old):
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 1, 1), **old)
    fri = entry(db, test_user, FRI_IN_WINDOW, t(8), t(12))
    impact = _run_change(db, test_user, test_admin, MON_THU)
    assert 4 in impact.changed_weekdays
    assert [(c.entry_id, c.new_net) for c in impact.reclamp.changed if c.date == FRI_IN_WINDOW] == [
        (fri.id, Decimal("0.00"))]
    assert "entries" in impact.shortening_reasons


def test_weekly_hours_only_change_touches_no_weekday(db, test_user, test_admin, monkeypatch):
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=20)
    eff = date(2026, 9, 1)
    impact = wh_change_service.run_change(
        db, test_user, admin_id=test_admin.id, effective_from=eff,
        apply=lambda: db.add(change_row(test_user, eff, weekly_hours=30)))
    assert impact.changed_weekdays == []
