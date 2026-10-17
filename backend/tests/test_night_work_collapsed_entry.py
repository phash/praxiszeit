"""Gesamtreview 1.20 (Fund 32): ein vollständig gekappter Eintrag ist keine Nachtarbeit.

Liegt ein Eintrag ganz hinter der Hülle (letzter Block + Puffer), kollabiert er
auf ``start_time == end_time`` (0 h angerechnet, Rohstempel bleiben, #201). Seit
1.20 kappt auch der Auto-Close — wer nach der Hülle einstempelt und das
Ausstempeln vergisst, bekommt genau so einen Eintrag. ``is_night_work`` las
Beginn == Ende als Schicht über Mitternacht (24 h) und meldete ihn als
Nachtarbeit: Badge in der Zeiterfassung, Zähler im Nachtarbeitsbericht (§ 2
Abs. 5 ArbZG, 48-Tage-Schwelle) und in den §16-Exporten.
"""
import datetime as dt
from datetime import time

from app.models import TimeEntry
from app.routers import reports
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON, block_week

import app.routers.time_entries as te

TUE = MON + dt.timedelta(days=1)


def _collapsed_by_auto_close(db, user, client, monkeypatch):
    # Hülle Mo 07:45–17:15; eingestempelt 19:00, Ausstempeln vergessen.
    user.work_blocks = block_week(mon=[("08:00", "17:00")])
    entry = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                      start_time=time(19, 0), end_time=None, break_minutes=0)
    db.add(entry)
    db.commit()
    monkeypatch.setattr(te, "_today_local", lambda: TUE)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 2, 7, 30))
    resp = client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text
    db.refresh(entry)
    # Kollaps: 0 h angerechnet, Rohstempel 19:00–23:59 bleibt (§16).
    assert (entry.start_time, entry.end_time, entry.raw_end_time) == (
        time(19, 0), time(19, 0), time(23, 59))
    return entry


def test_collapsed_entry_has_no_night_badge(_db_session, employee_user, employee_client, monkeypatch):
    entry = _collapsed_by_auto_close(_db_session, employee_user, employee_client, monkeypatch)
    rows = employee_client.get("/api/time-entries/", params={"month": "2026-06"}).json()
    row = next(r for r in rows if r["id"] == str(entry.id))
    assert row["is_night_work"] is False


def test_collapsed_entry_not_counted_in_night_work_summary(
    _db_session, employee_user, admin_user, employee_client, monkeypatch,
):
    _collapsed_by_auto_close(_db_session, employee_user, employee_client, monkeypatch)
    summary = reports.get_night_work_summary(year=2026, db=_db_session, current_user=admin_user)
    mine = next(e for e in summary["employees"] if e["user_id"] == str(employee_user.id))
    assert mine["night_work_days"] == 0
