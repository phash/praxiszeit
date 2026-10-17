"""Ultrareview: ``today_net_minutes`` der Stempelkarte (#494).

Fund 1: der LAUFENDE Eintrag zählte als Wanduhrzeit (jetzt − Beginn − Pause) und
ignorierte die Lücke zwischen den Arbeitszeit-Blöcken sowie das Hüllenende.
Mo–Fr 08–12 + 15–18, Puffer 15, eingestempelt 08:00, jetzt 16:00 → angerechnet
werden 330 Min. (Lücke 12:15–14:45 = 150 Min.), nicht 480 — dieselbe Regel wie
beim Ausstempeln (``work_window_service.clamp``).
"""
import datetime as dt

import pytest

from app.models import TimeEntry
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_494_clock_status_today import TODAY, _client, _clear_overrides, frozen_now  # noqa: F401
from tests.work_blocks_fixtures import block_week

THU_BLOCKS = block_week(thu=[("08:00", "12:00"), ("15:00", "18:00")])


def _open(db, user, start, *, raw_start=None, break_min=0, credit_override=False):
    db.add(TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=TODAY,
                     start_time=start, raw_start_time=raw_start, end_time=None,
                     break_minutes=break_min, credit_override=credit_override,
                     clamp_grace_minutes=15))
    db.commit()


@pytest.fixture
def blocks_user(db, test_user):
    test_user.work_blocks = THU_BLOCKS
    db.commit()
    return test_user


@pytest.mark.parametrize("now, start, raw_start, break_min, override, expected", [
    ((16, 0), dt.time(8), None, 0, False, 330),          # Lücke 12:15–14:45 abgezogen
    ((13, 0), dt.time(8), None, 0, False, 255),          # jetzt in der Lücke
    ((19, 0), dt.time(7, 45), dt.time(7), 0, False, 480),  # Hüllenende 18:15
    ((16, 0), dt.time(8), None, 30, False, 300),         # erfasste Pause zusätzlich
    ((7, 30), dt.time(7, 45), dt.time(7, 30), 0, False, 0),  # gekappter Beginn nach jetzt
    ((16, 0), dt.time(8), None, 0, True, 480),           # anerkannt: keine Kappung
])
def test_running_entry_counts_credited_minutes(db, blocks_user, frozen_now, now, start,
                                               raw_start, break_min, override, expected):
    frozen_now(*now)
    _open(db, blocks_user, start, raw_start=raw_start, break_min=break_min, credit_override=override)
    body = _client(db, blocks_user).get("/api/time-entries/clock-status").json()
    assert body["is_clocked_in"] is True
    assert body["today_net_minutes"] == expected

