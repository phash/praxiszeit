"""Gesamtreview 1.20, Bündel B1 (Punkt 1): §5-Ruhezeit und der automatisch
geschlossene Eintrag (P18).

Der Auto-Close schließt einen vergessenen Eintrag mit dem synthetischen Ende
23:59 und kappt es gegen die Hülle (``raw_end_time`` 23:59, ``end_time`` 18:15).
23:59 ist kein Stempel — niemand hat dort ausgestempelt. Alle drei §5-Lesestellen
(``clock_in``-Echtzeitwarnung, ``rest_time_service``, XLS-Vorschau) lasen bisher
``raw_end_time or end_time`` und meldeten am Folgetag eine Ruhezeit ab 23:59:
Einstempeln um 07:30 → „Nur 7.5h Ruhezeit", obwohl angerechnet (und belegt)
nur bis 18:15 gearbeitet wurde. Maßgeblich ist beim automatisch geschlossenen
Eintrag das wirksame Ende — wie bei der Anwesenheit (Spec 8.3,
``work_window_service.presence_minutes``). Ein echter Rohstempel (auch ein
eingetragenes 23:59, ``auto_closed`` = False) bleibt maßgeblich.
"""
import datetime as dt
from datetime import date, time

from app.models import TimeEntry
from app.services.rest_time_service import check_rest_time_violations
from app.services.xls_import_service import parse_xls
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, employee_client, employee_user, tenant,
)
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes
from tests.work_blocks_fixtures import K_BLOCKS, MON

import app.routers.time_entries as te

TUE = date(2026, 6, 2)
HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]


def _entry(db, user, d, start, end, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=0, **kw)
    db.add(e)
    db.commit()
    return e


def _auto_closed_monday(db, user):
    """Wie nach dem Auto-Close gegen K_BLOCKS: Hülle 07:45–18:15."""
    return _entry(db, user, MON, time(8), time(18, 15), raw_end_time=time(23, 59),
                  uncredited_minutes=150, auto_closed=True, clamp_grace_minutes=15)


# ── rest_time_service (Bericht „Ruhezeit-Verstöße") ─────────────────────────

def test_report_ignores_the_synthetic_end_of_an_auto_closed_entry(db, test_user):
    _auto_closed_monday(db, test_user)
    _entry(db, test_user, TUE, time(7, 30), time(12))
    # 18:15 → 07:30 = 13,25 h; mit 23:59 wären es 7,5 h (Phantomverstoß)
    assert check_rest_time_violations(db, test_user, 2026, month=6) == []


def test_report_keeps_a_real_2359_stamp(db, test_user):
    """Kontrolle: ein echtes Ende 23:59 (seit V1 eintragbar, Kennzeichen weg)
    ist ein Stempel und bleibt die Grundlage der Ruhezeit."""
    _entry(db, test_user, MON, time(8), time(18, 15), raw_end_time=time(23, 59),
           auto_closed=False)
    _entry(db, test_user, TUE, time(7, 30), time(12))
    [v] = check_rest_time_violations(db, test_user, 2026, month=6)
    assert (v["day1_end"], v["actual_rest_hours"]) == ("23:59:00", 7.52)


def test_report_auto_closed_without_blocks_stays_at_2359(db, test_user):
    """Grenzfall P18: ohne Blöcke ist das wirksame Ende selbst 23:59 — dann
    rechnet §5 (wie die Anrechnung) weiter bis 23:59."""
    _entry(db, test_user, MON, time(8), time(23, 59), auto_closed=True)
    _entry(db, test_user, TUE, time(7, 30), time(12))
    [v] = check_rest_time_violations(db, test_user, 2026, month=6)
    assert v["day1_end"] == "23:59:00"


# ── clock_in (Echtzeitwarnung) ──────────────────────────────────────────────

def _clock_in_tuesday(client, monkeypatch, at=time(7, 30)):
    monkeypatch.setattr(te, "_today_local", lambda: TUE)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime.combine(TUE, at))
    resp = client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text
    return resp.json()["warnings"]


def _rest_warnings(warnings):
    return [w for w in warnings if w.startswith("REST_TIME_WARNING")]


def test_clock_in_after_auto_close_in_the_same_request(_db_session, employee_user,
                                                       employee_client, monkeypatch):
    """Der Normalfall: Montag vergessen auszustempeln, Dienstag 07:30 einstempeln.
    Der Auto-Close läuft im selben Request — die Warnung las danach sein 23:59."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    _entry(_db_session, employee_user, MON, time(8), None)
    assert _rest_warnings(_clock_in_tuesday(employee_client, monkeypatch)) == []
    e = _db_session.query(TimeEntry).filter(TimeEntry.date == MON).one()
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)


def test_clock_in_after_a_stored_auto_closed_entry(_db_session, employee_user,
                                                   employee_client, monkeypatch):
    _auto_closed_monday(_db_session, employee_user)
    assert _rest_warnings(_clock_in_tuesday(employee_client, monkeypatch)) == []


def test_clock_in_still_warns_against_the_effective_end(_db_session, employee_user,
                                                        employee_client, monkeypatch):
    """Die Warnung bleibt, wenn schon das wirksame Ende zu spät war:
    18:15 → 04:00 = 9,75 h."""
    _auto_closed_monday(_db_session, employee_user)
    [w] = _rest_warnings(_clock_in_tuesday(employee_client, monkeypatch, at=time(4, 0)))
    assert "Nur 9.8h" in w


def test_clock_in_keeps_a_real_2359_stamp(_db_session, employee_user, employee_client,
                                          monkeypatch):
    _entry(_db_session, employee_user, MON, time(8), time(18, 15),
           raw_end_time=time(23, 59), auto_closed=False)
    [w] = _rest_warnings(_clock_in_tuesday(employee_client, monkeypatch))
    assert "Nur 7.5h" in w


# ── XLS-Vorschau (Spec 7.3, Vortag aus der Datenbank) ───────────────────────

def _preview_tuesday(db, user):
    xls = _make_xls_bytes([HEADER, _make_data_row(_dt(2026, 6, 2, 7, 30), _dt(2026, 6, 2, 12, 0))])
    [row] = parse_xls(xls, user.id, db)
    return [w for w in row.arbzg_warnings if w.startswith("§5")]


def test_xls_preview_ignores_the_synthetic_end(db, test_user):
    _auto_closed_monday(db, test_user)
    assert _preview_tuesday(db, test_user) == []


def test_xls_preview_keeps_a_real_2359_stamp(db, test_user):
    _entry(db, test_user, MON, time(8), time(18, 15), raw_end_time=time(23, 59),
           auto_closed=False)
    [w] = _preview_tuesday(db, test_user)
    assert w.startswith("§5 ArbZG: Ruhezeit 7.5h"), w
