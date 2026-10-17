"""Spec 2026-10-08 (PR2): lesende Antwortfelder der Zeiteinträge (7.1, E79,
P18, P19) und der Notiztext der Anrechnung (10.1, 13.3)."""
from datetime import time

import pytest

from app.models import TimeEntry
from app.schemas.change_request import ChangeRequestCreate
from app.schemas.time_entry import ClockOutRequest, TimeEntryCreate, TimeEntryUpdate
from app.services import work_window_service as wws
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON

SERVER_ONLY = {
    "uncredited_minutes", "credit_override", "auto_closed",
    "clamp_grace_minutes", "not_credited_minutes",
}


def _te(start, end, brk=0, unc=0, **kw):
    return TimeEntry(start_time=start, end_time=end, break_minutes=brk,
                     uncredited_minutes=unc, **kw)


@pytest.mark.parametrize("entry, text", [
    # K1: nur Lücke — die Beispiele aus 10.1/13.3 nennen „davon …" auch hier.
    (_te(time(8), time(18), unc=150),
     "angerechnet 7:30 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken"),
    # K7: Hülle und Lücke
    (_te(time(7, 45), time(18, 15), unc=150, raw_start_time=time(7), raw_end_time=time(19)),
     "angerechnet 8:00 h, nicht angerechnet 4:00 h, davon 2:30 h zwischen den Blöcken"),
    # K9: Pause folgt am Ende
    (_te(time(8), time(18), brk=30, unc=150),
     "angerechnet 7:00 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken, Pause 0:30 h"),
    # nur Hülle: kein „davon"
    (_te(time(7, 45), time(16), brk=30, raw_start_time=time(7, 30)),
     "angerechnet 7:45 h, nicht angerechnet 0:15 h, Pause 0:30 h"),
    # nichts gekappt
    (_te(time(8), time(18)), "angerechnet 10:00 h"),
    # K15 Auto-Close: die synthetische Endseite (23:59) zählt nicht (P18)
    (_te(time(8), time(18, 15), unc=150, raw_end_time=time(23, 59), auto_closed=True),
     "angerechnet 7:45 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken"),
], ids=["K1", "K7", "K9", "hull", "plain", "K15"])
def test_credit_summary_text(entry, text):
    assert wws.credit_summary_text(entry) == text


def test_response_carries_the_read_only_fields(_db_session, employee_user, employee_client):
    employee_user.work_blocks = K_BLOCKS
    e = _te(time(7, 45), time(18, 15), unc=150, raw_start_time=time(7), raw_end_time=time(19),
            tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON, clamp_grace_minutes=15)
    _db_session.add(e)
    _db_session.commit()
    r = employee_client.get(f"/api/time-entries/{e.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uncredited_minutes"] == 150
    assert body["not_credited_minutes"] == 240   # P19: Lücke + Hülle (K7)
    assert body["credit_override"] is False
    assert body["auto_closed"] is False
    assert body["clamp_grace_minutes"] == 15
    assert body["net_hours"] == 8.0


def test_list_and_auto_closed_entry(_db_session, employee_user, employee_client):
    e = _te(time(8), time(18, 15), unc=150, raw_end_time=time(23, 59), auto_closed=True,
            tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON)
    _db_session.add(e)
    _db_session.commit()
    rows = employee_client.get("/api/time-entries/?month=2026-06").json()
    row = next(r for r in rows if r["id"] == str(e.id))
    assert (row["auto_closed"], row["not_credited_minutes"]) == (True, 150)


@pytest.mark.parametrize(
    "schema", [TimeEntryCreate, TimeEntryUpdate, ClockOutRequest, ChangeRequestCreate],
)
def test_server_side_fields_are_never_inputs(schema):
    assert SERVER_ONLY.isdisjoint(schema.model_fields), schema.__name__
