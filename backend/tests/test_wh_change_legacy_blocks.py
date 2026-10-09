"""Spec 2026-10-08 (PR1): Verlauf und Altfenster — P2, E8, E9, 3.3.

Bis PR3 kennt der Dialog keine Blöcke. Eine Wochenstunden-Änderung für eine
Person mit Altfenster muss die Kappung ab dem Wirkungsdatum deshalb
UNVERÄNDERT weiterlaufen lassen (P2: Übernahme aus dem Vorgänger-Snapshot),
die Basis-Zeile friert das Fenster der Vergangenheit ein (E8), und die
User-Zeile spiegelt die jüngste Zeile ≤ heute (E9).
"""
from datetime import date, time
from decimal import Decimal

from app.models import WorkingHoursChange
from app.routers.admin_users import _carried_blocks, _comparable_snapshot
from app.services import calculation_service, work_blocks_service
from app.services import work_window_service as wws
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, legacy_week

LEGACY = legacy_week(mon=("08:00", "17:00"))
LEGACY_LATER = legacy_week(mon=("09:00", "17:00"))
EFFECTIVE = date(2026, 6, 1)   # Montag, in der Vergangenheit
# Ein gewöhnlicher Montag vor dem Wirkungsdatum — bewusst NICHT der 25.05.2026
# (Pfingstmontag): ein Feiertag hat keine Blöcke (#484), und der prozessweite
# Feiertags-Cache (F-034) kann aus einem früheren Test der Vollsuite stammen.
EARLIER_MON = date(2026, 5, 18)
LATER_MON = date(2026, 6, 8)


def _row(db, user, effective_from, blocks, weekly_hours=40):
    row = WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=effective_from,
        weekly_hours=weekly_hours, use_daily_schedule=False, work_days_per_week=5,
        blocks=blocks,
    )
    db.add(row)
    db.commit()
    return row


def _rows(db, user):
    return (
        db.query(WorkingHoursChange)
        .filter(WorkingHoursChange.user_id == user.id,
                WorkingHoursChange.tenant_id == DEFAULT_TENANT_ID)
        .order_by(WorkingHoursChange.effective_from)
        .all()
    )


def _post(client, user, effective_from, weekly_hours):
    return client.post(f"/api/admin/users/{user.id}/working-hours-changes", json={
        "effective_from": effective_from.isoformat(), "weekly_hours": weekly_hours})


# Review Focus 4: neue Wochenstunden-Änderung für eine Person mit Altfenster.
def test_change_carries_legacy_window_and_freezes_the_past(_db_session, employee_user, admin_client):
    employee_user.work_blocks = LEGACY
    _db_session.commit()
    resp = _post(admin_client, employee_user, EFFECTIVE, 30)
    assert resp.status_code == 201, resp.text
    assert resp.json()["blocks"] == LEGACY
    rows = _rows(_db_session, employee_user)
    assert [r.effective_from for r in rows] == [date(2026, 5, 31), EFFECTIVE]  # Basis-Zeile + neue
    assert [r.blocks for r in rows] == [LEGACY, LEGACY]
    _db_session.refresh(employee_user)
    assert employee_user.work_blocks == LEGACY
    for d in (EARLIER_MON, LATER_MON):
        r = wws.clamp(_db_session, employee_user, d, time(7, 0), time(18, 0), 15,
                      credit_override=False)
        assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == (
            time(7, 45), time(17, 15), time(7, 0), time(18, 0)), d


def test_inserted_row_takes_window_of_its_predecessor(_db_session, employee_user, admin_client):
    """Spec 4.3: eine Zeile zwischen eine mit und eine ohne Fenster eingefügt
    übernimmt das Fenster; die Folgezeile bleibt ohne."""
    employee_user.work_blocks = None
    _row(_db_session, employee_user, date(2026, 1, 1), LEGACY)
    _row(_db_session, employee_user, date(2026, 9, 1), None)
    resp = _post(admin_client, employee_user, date(2026, 5, 4), 30)
    assert resp.status_code == 201, resp.text
    assert [(r.effective_from, r.blocks) for r in _rows(_db_session, employee_user)] == [
        (date(2026, 1, 1), LEGACY), (date(2026, 5, 4), LEGACY), (date(2026, 9, 1), None)]


def test_new_blocks_end_with_a_change_without_blocks(_db_session, employee_user, admin_client):
    """P24: neue Blöcke (Pause gesetzt) laufen NICHT in eine Zeile des Modus
    „Gleichmäßig" hinein; die Vorgängerzeile behält ihre Blöcke."""
    _row(_db_session, employee_user, date(2026, 1, 1), K_BLOCKS)
    resp = _post(admin_client, employee_user, date(2026, 5, 4), 30)
    assert resp.status_code == 201, resp.text
    assert [r.blocks for r in _rows(_db_session, employee_user)] == [K_BLOCKS, None]


def test_delete_resyncs_the_user_mirror(_db_session, employee_user, admin_client):
    _row(_db_session, employee_user, date(2026, 1, 1), LEGACY)
    later = _row(_db_session, employee_user, date(2026, 6, 1), LEGACY_LATER, weekly_hours=30)
    employee_user.work_blocks = LEGACY_LATER
    _db_session.commit()
    resp = admin_client.delete(f"/api/admin/users/{employee_user.id}/working-hours-changes/{later.id}")
    assert resp.status_code in (200, 204), resp.text
    _db_session.refresh(employee_user)
    assert employee_user.work_blocks == LEGACY


def test_list_returns_blocks(_db_session, employee_user, admin_client):
    _row(_db_session, employee_user, date(2026, 1, 1), LEGACY)
    listed = admin_client.get(f"/api/admin/users/{employee_user.id}/working-hours-changes").json()
    assert [r["blocks"] for r in listed] == [LEGACY]


def test_carried_blocks_rule():
    legacy = work_blocks_service.parse_week_blocks(LEGACY)
    new = work_blocks_service.parse_week_blocks(K_BLOCKS)

    def schedule(parsed):
        return calculation_service.Schedule(
            weekly_hours=Decimal("40"), use_daily_schedule=False, day_hours=(None,) * 5,
            work_days_per_week=5,
            blocks=parsed.blocks if parsed else None,
            block_pauses=parsed.pauses if parsed else None,
        )

    assert _carried_blocks(schedule(legacy)) == (legacy.blocks, legacy.pauses)
    assert _carried_blocks(schedule(new)) == (None, None)
    assert _carried_blocks(schedule(None)) == (None, None)


def test_comparable_snapshot_sees_blocks():
    legacy = work_blocks_service.parse_week_blocks(LEGACY)
    plain = _comparable_snapshot(40, False, (None,) * 5, 5, None, None)
    assert plain == _comparable_snapshot(40.0, False, (None,) * 5, 5, None, None)
    assert plain != _comparable_snapshot(40, False, (None,) * 5, 5, legacy.blocks, legacy.pauses)
