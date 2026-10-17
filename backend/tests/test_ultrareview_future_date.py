"""Ultrareview 1.20 (Fund 2): Einträge mit einem Datum in der Zukunft.

(a) Der XLS-Import überspringt Zeilen mit einem Datum nach heute sichtbar —
    wie Zeilen außerhalb des Beschäftigungsfensters (Vorschau-Hinweis,
    ``/confirm``-Warnung, ersetzt keinen Bestand, zählt für keinen Tag). Bis
    dahin legte ``/confirm`` sie still an (``ImportedEntryIn`` kennt keine
    Zukunftsprüfung).
(b) Beim Bearbeiten greift die Zukunftsprüfung nur bei einem tatsächlichen
    Datumswechsel. ``TimeEntryUpdate`` lehnte jedes Datum nach heute ab, auch
    das unverändert mitgeschickte — AdminDashboard und Zeiterfassung schicken
    das Datum immer mit, ein künftig datierter Eintrag war damit nicht mehr
    korrigierbar (nur löschbar)."""
from datetime import date, time, timedelta

import pytest

from app.models import TimeEntry
from app.services import xls_import_service
from app.services.timezone_service import today_local
from app.services.xls_import_service import ImportedEntry, execute_import, parse_xls
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes

HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]
TODAY = date(2026, 9, 23)        # Mittwoch
FUTURE = date(2026, 9, 24)       # Donnerstag
NOTE = "Wird übersprungen — Datum liegt in der Zukunft."


@pytest.fixture
def today_is_wed(monkeypatch):
    monkeypatch.setattr(xls_import_service, "today_local", lambda: TODAY)


def _xls(*rows):
    return _make_xls_bytes([HEADER, *[_make_data_row(a, b) for a, b in rows]])


def _at(d, h, m=0):
    return _dt(d.year, d.month, d.day, h, m)


def _run(db, user, admin, rows, overwrite=False):
    return execute_import(user.id, rows, overwrite=overwrite, db=db, changed_by_id=admin.id,
                          filename="zukunft.xls", tenant_id=DEFAULT_TENANT_ID)


def _stored(db, user):
    db.expire_all()
    return [
        (e.date, e.start_time, e.end_time)
        for e in db.query(TimeEntry).filter(TimeEntry.user_id == user.id)
        .order_by(TimeEntry.date, TimeEntry.start_time).all()
    ]


def test_preview_marks_a_future_row(db, test_user, today_is_wed):
    rows = parse_xls(_xls((_at(TODAY, 8), _at(TODAY, 12)), (_at(FUTURE, 6), _at(FUTURE, 18))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    assert NOTE not in rows[0].arbzg_warnings, rows[0].arbzg_warnings
    # Nur der Hinweis — 06:00–18:00 löste sonst §3 aus.
    assert rows[1].arbzg_warnings == [NOTE]
    assert (rows[1].has_conflict, rows[1].break_minutes) == (False, 0)


def test_confirm_skips_a_future_row_itself(db, test_user, test_admin, today_is_wed):
    """``/confirm`` nimmt die Zeilen vom Client — ohne Vorschau-Hinweis wird
    trotzdem übersprungen."""
    forged = ImportedEntry(date=FUTURE, start_time=time(8), end_time=time(12), break_minutes=0,
                           note=None, has_conflict=False, arbzg_warnings=[])
    kept = ImportedEntry(date=TODAY, start_time=time(8), end_time=time(12), break_minutes=0,
                         note=None, has_conflict=False, arbzg_warnings=[])
    result = _run(db, test_user, test_admin, [kept, forged])
    assert (result.imported, result.skipped) == (1, 1)
    assert "24.09.2026: übersprungen — Datum liegt in der Zukunft." in result.warnings
    assert _stored(db, test_user) == [(TODAY, time(8), time(12))]


def test_future_row_replaces_no_entry_even_with_overwrite(db, test_user, test_admin,
                                                          today_is_wed):
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=FUTURE,
                     start_time=time(8), end_time=time(12), break_minutes=0))
    db.commit()
    rows = parse_xls(_xls((_at(FUTURE, 8), _at(FUTURE, 13))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    assert (rows[0].has_conflict, rows[0].arbzg_warnings) == (False, [NOTE])
    result = _run(db, test_user, test_admin, rows, overwrite=True)
    assert (result.imported, result.overwritten, result.skipped) == (0, 0, 1)
    assert _stored(db, test_user) == [(FUTURE, time(8), time(12))]


# ── (b) Bearbeiten: nur ein Datumswechsel in die Zukunft scheitert ───────────

ROUTES = ["/api/time-entries/{id}", "/api/admin/time-entries/{id}"]


def _future_entry(db, user):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id,
                  date=today_local() + timedelta(days=2),
                  start_time=time(8), end_time=time(12), break_minutes=0, note="alt")
    db.add(e)
    db.commit()
    return e


@pytest.mark.parametrize("route", ROUTES)
def test_unchanged_future_date_does_not_block_the_edit(_db_session, employee_user,
                                                       admin_client, route):
    e = _future_entry(_db_session, employee_user)
    resp = admin_client.put(route.format(id=e.id), json={
        "date": e.date.isoformat(), "note": "neu"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.note == "neu"


@pytest.mark.parametrize("route", ROUTES)
def test_move_to_another_future_date_is_rejected(_db_session, employee_user, admin_client,
                                                 route):
    e = _future_entry(_db_session, employee_user)
    old = e.date
    resp = admin_client.put(route.format(id=e.id), json={
        "date": (old + timedelta(days=1)).isoformat()})
    assert (resp.status_code, resp.json()["detail"]) == (
        422, "Datum darf nicht in der Zukunft liegen")
    _db_session.refresh(e)
    assert e.date == old


@pytest.mark.parametrize("route", ROUTES)
def test_future_entry_can_be_moved_to_today(_db_session, employee_user, admin_client, route):
    e = _future_entry(_db_session, employee_user)
    resp = admin_client.put(route.format(id=e.id), json={"date": today_local().isoformat()})
    assert resp.status_code == 200, resp.text
