"""Spec E13 / 7.1: nicht angerechnete Minuten in net_hours und den Netto-Helfern."""
from datetime import time

import pytest

from app.models import TimeEntry
from app.routers.time_entries import (
    _calculate_daily_net_hours, _calculate_weekly_net_hours, _net_hours,
)
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import MON


def test_net_hours_helper_subtracts_uncredited():
    assert _net_hours(time(8, 0), time(18, 0), 0, 150) == 7.5
    assert _net_hours(time(12, 30), time(14, 30), 0, 120) == 0.0


def test_net_hours_helper_requires_uncredited():
    with pytest.raises(TypeError):
        _net_hours(time(8, 0), time(18, 0), 0)


def test_daily_and_weekly_sum_use_stored_uncredited(db, test_user):
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                     start_time=time(8, 0), end_time=time(18, 0), break_minutes=0,
                     uncredited_minutes=150))
    db.commit()
    kwargs = dict(db=db, user_id=test_user.id, entry_date=MON, start_time=time(19, 0),
                  end_time=time(20, 0), break_minutes=0, uncredited_minutes=0,
                  tenant_id=DEFAULT_TENANT_ID)
    assert _calculate_daily_net_hours(**kwargs) == 8.5
    assert _calculate_weekly_net_hours(**kwargs) == 8.5


def test_helpers_require_uncredited_keyword(db, test_user):
    with pytest.raises(TypeError):
        _calculate_daily_net_hours(db=db, user_id=test_user.id, entry_date=MON,
                                   start_time=time(8), end_time=time(9), break_minutes=0)
    with pytest.raises(TypeError):
        _calculate_weekly_net_hours(db=db, user_id=test_user.id, entry_date=MON,
                                    start_time=time(8), end_time=time(9), break_minutes=0)


def test_transient_entry_without_flush_counts_zero():
    """``or 0``: vor dem flush greift der Spalten-Default noch nicht."""
    e = TimeEntry(start_time=time(8, 0), end_time=time(9, 0), break_minutes=0)
    e.uncredited_minutes = None
    assert str(e.net_hours) == "1.0"
