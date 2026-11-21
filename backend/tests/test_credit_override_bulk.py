"""Plan 2026-11-21 Task 9 (Spec 7, Teil 2B): Sammel-Anerkennen im Monatsjournal —
``POST /api/admin/users/{user_id}/time-entries/credit-override``.

Alles oder nichts, idempotent, 404 vor jeder Sperre (P5), F-026. Die
Nebenläufigkeit unter echten Zeilensperren prüft ``test_credit_override_bulk_pg.py``."""
import uuid
from datetime import time

from app.models import TimeEntry, TimeEntryAuditLog
from app.services import credit_override_service as cos
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.test_write_path_locks import (  # noqa: F401 — Fixture ``calls``
    _other_employee, assert_lock_first, assert_row_lock_seen, calls,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON

# Feste IDs: der gute Eintrag sortiert VOR dem automatisch geschlossenen. So ist
# er schon anerkannt, wenn der zweite scheitert — der Test sieht das Zurückrollen.
LOW_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
HIGH_ID = uuid.UUID("ffffffff-0000-4000-8000-000000000001")


def _entry(db, user, start, end, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=kw.pop("day", MON),
                  start_time=start, end_time=end, break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def _clamped(db, user, start, end, raw_start, raw_end, uncredited, **kw):
    """Ein gekappter Eintrag wie nach einer Neukappung (Rohstempel daneben)."""
    user.work_blocks = K_BLOCKS
    return _entry(db, user, start, end, raw_start_time=raw_start, raw_end_time=raw_end,
                  uncredited_minutes=uncredited, clamp_grace_minutes=15, **kw)


def _url(user):
    return f"/api/admin/users/{user.id}/time-entries/credit-override"


def _post(client, user, *ids):
    return client.post(_url(user), json={"entry_ids": [str(i) for i in ids]})


def _override_logs(db):
    return db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.source == cos.CREDIT_OVERRIDE_SOURCE).all()


def test_bulk_recognizes_all(_db_session, employee_user, admin_user, admin_client):
    a = _clamped(_db_session, employee_user, time(7, 45), time(12, 0), time(7), time(12), 45)
    b = _clamped(_db_session, employee_user, time(13, 0), time(18, 15), time(13), time(19), 45)
    r = _post(admin_client, employee_user, a.id, b.id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["recognized"], body["already"]) == (2, 0)
    assert isinstance(body["warnings"], list)
    _db_session.expire_all()
    for e, (start, end) in ((a, (time(7), time(12))), (b, (time(13), time(19)))):
        got = _db_session.get(TimeEntry, e.id)
        assert got.credit_override is True
        assert (got.start_time, got.end_time, got.uncredited_minutes) == (start, end, 0)
        assert (got.raw_start_time, got.raw_end_time) == (None, None)
    logs = _override_logs(_db_session)
    assert sorted(str(log.time_entry_id) for log in logs) == sorted([str(a.id), str(b.id)])
    assert all(log.changed_by == admin_user.id and log.row_hash for log in logs)


def test_bulk_idempotent(_db_session, employee_user, admin_client):
    done = _entry(_db_session, employee_user, time(7), time(12), credit_override=True)
    fresh = _clamped(_db_session, employee_user, time(13, 0), time(18, 15), time(13), time(19), 45)
    r = _post(admin_client, employee_user, done.id, fresh.id)
    assert r.status_code == 200, r.text
    assert (r.json()["recognized"], r.json()["already"]) == (1, 1)
    # Der schon anerkannte Eintrag bekommt keine zweite Protokollzeile.
    assert [str(log.time_entry_id) for log in _override_logs(_db_session)] == [str(fresh.id)]


def test_bulk_duplicate_ids_count_once(_db_session, employee_user, admin_client):
    e = _clamped(_db_session, employee_user, time(7, 45), time(12, 0), time(7), time(12), 45)
    r = _post(admin_client, employee_user, e.id, e.id)
    assert r.status_code == 200, r.text
    assert (r.json()["recognized"], r.json()["already"]) == (1, 0)
    assert len(_override_logs(_db_session)) == 1


def test_bulk_all_or_nothing_auto_closed(_db_session, employee_user, admin_client):
    """Review Focus 5: ein automatisch geschlossener Eintrag in der Auswahl →
    400 mit Datum vorne und ``AUTO_CLOSED_DETAIL`` hinten; der vorher
    anerkannte Eintrag ist zurückgerollt, kein Protokoll."""
    good = _clamped(_db_session, employee_user, time(7, 45), time(12, 0), time(7), time(12), 45, id=LOW_ID)
    closed = _entry(_db_session, employee_user, time(13), time(18, 15), id=HIGH_ID,
                    raw_end_time=time(23, 59), auto_closed=True, clamp_grace_minutes=15)
    r = _post(admin_client, employee_user, closed.id, good.id)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail.startswith(MON.strftime("%d.%m.%Y") + ": "), detail
    assert detail.endswith(cos.AUTO_CLOSED_DETAIL), detail
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, good.id).credit_override is False
    assert _db_session.get(TimeEntry, good.id).raw_start_time == time(7)
    assert _db_session.get(TimeEntry, closed.id).credit_override is False
    assert _override_logs(_db_session) == []


def test_bulk_open_entry_rejected_with_date(_db_session, employee_user, admin_client):
    good = _clamped(_db_session, employee_user, time(7, 45), time(12, 0), time(7), time(12), 45, id=LOW_ID)
    open_entry = _entry(_db_session, employee_user, time(13), None, id=HIGH_ID)
    r = _post(admin_client, employee_user, good.id, open_entry.id)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == f"{MON.strftime('%d.%m.%Y')}: {cos.OPEN_ENTRY_DETAIL}"
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, good.id).credit_override is False


def test_bulk_foreign_entry_404_no_lock(_db_session, employee_user, admin_client, calls):
    """Review Focus 2 (wie Task 4): der Eintrag einer anderen Person derselben
    Praxis im Body → 404 ohne Anker- und ohne Zeilensperre, nichts gespeichert."""
    own = _clamped(_db_session, employee_user, time(7, 45), time(12, 0), time(7), time(12), 45)
    foreign = _entry(_db_session, _other_employee(_db_session), time(8), time(11))
    r = _post(admin_client, employee_user, own.id, foreign.id)
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Zeiteintrag nicht gefunden"
    assert not [c for c in calls if c[0] == "lock"], calls
    assert ("row_lock",) not in calls, calls
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, own.id).credit_override is False
    assert _db_session.get(TimeEntry, foreign.id).credit_override is False


def test_bulk_unknown_entry_404_no_lock(_db_session, employee_user, admin_client, calls):
    r = _post(admin_client, employee_user, uuid.uuid4())
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Zeiteintrag nicht gefunden"
    assert not [c for c in calls if c[0] == "lock"], calls
    assert ("row_lock",) not in calls, calls


def test_bulk_locks_anchor_first(_db_session, employee_user, admin_client, calls):
    """P5: Ankersperre der Person vor der ersten Zeilensperre."""
    e = _clamped(_db_session, employee_user, time(7, 45), time(12, 0), time(7), time(12), 45)
    assert _post(admin_client, employee_user, e.id).status_code == 200
    assert_lock_first(calls, employee_user.id)
    assert_row_lock_seen(calls)


def test_bulk_unknown_user_404(_db_session, employee_user, admin_client):
    e = _entry(_db_session, employee_user, time(8), time(11))
    r = admin_client.post(f"/api/admin/users/{uuid.uuid4()}/time-entries/credit-override",
                          json={"entry_ids": [str(e.id)]})
    assert r.status_code == 404, r.text


def test_bulk_rejects_201_ids(_db_session, employee_user, admin_client):
    r = _post(admin_client, employee_user, *[uuid.uuid4() for _ in range(201)])
    assert r.status_code == 422, r.text
    assert cos.RECOGNIZE_LIMIT_DETAIL in r.text


def test_bulk_rejects_empty_list(_db_session, employee_user, admin_client):
    assert _post(admin_client, employee_user).status_code == 422


def test_bulk_requires_admin(_db_session, employee_user, employee_client):
    e = _entry(_db_session, employee_user, time(8), time(11))
    assert _post(employee_client, employee_user, e.id).status_code == 403
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id).credit_override is False


def test_bulk_warnings_deduplicated(_db_session, employee_user, admin_client):
    """Zwei Einträge desselben Tages mit zusammen 12 h: die Tageswarnung (§3)
    entsteht je Eintrag gleich und steht in der Antwort nur einmal."""
    a = _entry(_db_session, employee_user, time(7), time(13))
    b = _entry(_db_session, employee_user, time(13, 45), time(19, 45))
    r = _post(admin_client, employee_user, a.id, b.id)
    assert r.status_code == 200, r.text
    warnings = r.json()["warnings"]
    assert len(warnings) == len(set(warnings)), warnings
    assert len([w for w in warnings if w.startswith("DAILY_HOURS_HARD")]) == 1, warnings
