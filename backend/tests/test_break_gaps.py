"""Spec 8.2: §4 mit Lückensegmenten; 7.3: Mandantenfilter."""
import uuid
from datetime import time

from app.models import TimeEntry
from app.models.tenant import Tenant
from app.services.break_validation_service import (
    BreakBlock, break_block_for_new, daily_break_figures, validate_daily_break,
)
from app.services import work_window_service as wws
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

# Lücke 12:15–12:25 (Hülle bis 12:15, ab 12:25): ein Segment von 10 Minuten —
# wird abgezogen, zählt aber nicht als Pausenabschnitt (unter 15 Minuten).
SHORT_GAP = block_week(mon=[("08:00", "12:00"), ("12:40", "17:00")])


def _validate(db, user, start, end, brk=0, segs=(), **kw):
    return validate_daily_break(db, user, MON, start, end, brk, uncredited_segments=list(segs),
                                tenant_id=DEFAULT_TENANT_ID, **kw)


def test_gap_segment_counts_as_break_k1(db, test_user):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    segs = wws.gap_segments(db, test_user, MON, time(8), time(18), 15, credit_override=False)
    assert segs == [150]
    assert _validate(db, test_user, time(8), time(18), 0, segs) is None


def test_segment_below_15_is_deducted_but_no_break(db, test_user):
    test_user.work_blocks = SHORT_GAP
    db.commit()
    segs = wws.gap_segments(db, test_user, MON, time(8), time(17), 15, credit_override=False)
    assert segs == [10]
    error = _validate(db, test_user, time(8), time(17), 0, segs)
    # Abzug: 540 − 10 = 530 Min (ohne Abzug stünde dort 9h 0min); keine Pause:
    # das 10-Minuten-Segment ist kein Abschnitt (sonst „Gesamtpause: 10").
    assert error is not None and "30 Minuten" in error
    assert "8h 50min" in error and "Gesamtpause: 0 Minuten" in error, error


def test_segment_below_15_deduction_pulls_under_six_hours(db, test_user):
    """8.2: der Abzug wirkt auch bei Segmenten unter 15 Minuten — 08:00–14:05
    sind brutto 365 Min, angerechnet 355 Min (≤ 6 h), also keine Pausenpflicht."""
    test_user.work_blocks = SHORT_GAP
    db.commit()
    segs = wws.gap_segments(db, test_user, MON, time(8), time(14, 5), 15, credit_override=False)
    assert segs == [10]
    assert _validate(db, test_user, time(8), time(14, 5), 0, segs) is None


def test_existing_entry_segment_below_15_is_no_break(db, test_user):
    """8.2: auch beim BESTEHENDEN Eintrag zählt ein Segment unter 15 Minuten
    nicht als Pausenabschnitt; abgezogen wird der gespeicherte Wert.
    530 + 30 = 560 Min Arbeit, Pause 0."""
    test_user.work_blocks = SHORT_GAP
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                     start_time=time(8), end_time=time(17), break_minutes=0,
                     uncredited_minutes=10, clamp_grace_minutes=15))
    db.commit()
    error = _validate(db, test_user, time(17), time(17, 30), 0, ())
    assert error is not None and "45 Minuten" in error, error
    assert "9h 20min" in error and "Gesamtpause: 0 Minuten" in error, error


def test_existing_entry_segments_use_its_own_grace(db, test_user):
    """8.2/E80: Segmente bestehender Einträge mit deren GESPEICHERTEM Puffer —
    mit dem aktuellen Puffer 0 wäre die Lücke 180 ≠ 150 und zählte nicht."""
    from app.models.system_setting import SystemSetting
    db.add(SystemSetting(key="work_window_grace_minutes", value="0", tenant_id=DEFAULT_TENANT_ID))
    test_user.work_blocks = K_BLOCKS
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                     start_time=time(8), end_time=time(18), break_minutes=0,
                     uncredited_minutes=150, clamp_grace_minutes=15))
    db.commit()
    # direkt anschließend: kein Abstand zwischen den Einträgen, Pause nur aus der Lücke
    assert _validate(db, test_user, time(18, 0), time(18, 30), 0, ()) is None


def test_stored_uncredited_differs_from_segments_counts_strictly(db, test_user):
    """8.2: gespeichertes uncredited ≠ Σ Segmente → Abzug, aber kein Pausenabschnitt."""
    test_user.work_blocks = K_BLOCKS
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                     start_time=time(8), end_time=time(18), break_minutes=0,
                     uncredited_minutes=100, clamp_grace_minutes=15))
    db.commit()
    error = _validate(db, test_user, time(18, 0), time(18, 30), 0, ())
    assert error is not None and "30 Minuten" in error  # 530 Min Arbeit, keine Pause gezählt


def test_credit_override_entry_has_no_segments(db, test_user):
    """8.2: anerkannter Eintrag (``credit_override``) liefert keine Segmente —
    die Lücke ist dort angerechnete Arbeitszeit und keine Pause."""
    test_user.work_blocks = K_BLOCKS
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                     start_time=time(8), end_time=time(18), break_minutes=0,
                     uncredited_minutes=0, credit_override=True))
    db.commit()
    error = _validate(db, test_user, time(18, 0), time(18, 30), 0, ())
    assert error is not None and "45 Minuten" in error  # 630 Min Arbeit, keine Pause


def test_other_tenant_rows_are_ignored(db, test_user):
    """Fremde Zeile 08:00–14:00 + neuer Eintrag 14:00–15:00 ergäbe 7 h ohne
    Pause — ignoriert bleibt 1 h."""
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    db.add(other)
    db.add(TimeEntry(tenant_id=other.id, user_id=test_user.id, date=MON,
                     start_time=time(8), end_time=time(14), break_minutes=0))
    db.commit()
    assert _validate(db, test_user, time(14), time(15), 0, ()) is None


def test_daily_break_figures_without_blocks_is_byte_identical():
    blocks = [BreakBlock(480, 720, 0, 0, ()), break_block_for_new(time(12, 30), time(17), 15, [])]
    assert daily_break_figures(blocks) == ((240 + 270) - 15, 15 + 30)


# ---------------------------------------------------------------------------
# Spec 8.2: jede §4-Aufrufstelle reicht die Lückensegmente des neuen bzw.
# geänderten Eintrags durch. K1 (08:00–18:00 ohne Pause, Lücke 12:15–14:45):
# angerechnet 7:30 h, die Lücke deckt die Pause (150 Min ≥ 30). Ohne Segmente
# sähe §4 auf der Hülle 10 h ohne Pause → 400 (bzw. 422 in der Genehmigung).
# Der MA-Antragsweg prüft bis E40 (Task 9) roh und bleibt hier außen vor.
# ---------------------------------------------------------------------------
from datetime import time as _time  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402

from app.models import ChangeRequest  # noqa: E402
from app.models.change_request import ChangeRequestStatus, ChangeRequestType  # noqa: E402
from tests.test_endpoints import (  # noqa: E402,F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.test_write_paths_uncredited import _blocks, _entry, _today  # noqa: E402

K1 = {"start_time": "08:00", "end_time": "18:00", "break_minutes": 0}


def _k1_ma_create(db, user, request):
    return request.getfixturevalue("employee_client").post(
        "/api/time-entries/", json={"date": MON.isoformat(), **K1})


def _k1_ma_update(db, user, request):
    e = _entry(db, user, _time(8, 0), _time(12, 0))
    return request.getfixturevalue("employee_client").put(f"/api/time-entries/{e.id}", json=K1)


def _k1_admin_create(db, user, request):
    return request.getfixturevalue("admin_client").post(
        f"/api/admin/users/{user.id}/time-entries", json={"date": MON.isoformat(), **K1})


def _k1_admin_update(db, user, request):
    e = _entry(db, user, _time(8, 0), _time(12, 0))
    return request.getfixturevalue("admin_client").put(f"/api/admin/time-entries/{e.id}", json=K1)


def _k1_cr_approval(db, user, request):
    cr = ChangeRequest(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
                       proposed_date=MON, proposed_start_time=_time(8, 0), proposed_end_time=_time(18, 0),
                       proposed_break_minutes=0, reason="Nachtrag")
    db.add(cr)
    db.commit()
    return request.getfixturevalue("admin_client").post(
        f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})


def _k1_clock_out(db, user, request, monkeypatch):
    _entry(db, user, _time(8, 0), None)
    _today(monkeypatch, 18, 0)
    return request.getfixturevalue("employee_client").post(
        "/api/time-entries/clock-out", json={"break_minutes": 0})


@pytest.mark.parametrize("path, expected_status", [
    (_k1_ma_create, 201), (_k1_ma_update, 200), (_k1_admin_create, 201),
    (_k1_admin_update, 200), (_k1_cr_approval, 200), (_k1_clock_out, 200),
], ids=["ma_create", "ma_update", "admin_create", "admin_update", "cr_approval", "clock_out"])
def test_write_paths_count_gap_segment_as_break(_db_session, employee_user, request, monkeypatch,
                                                path, expected_status):
    _blocks(_db_session, employee_user)
    _today(monkeypatch, 19, 30)
    if path is _k1_clock_out:
        resp = path(_db_session, employee_user, request, monkeypatch)
    else:
        resp = path(_db_session, employee_user, request)
    assert resp.status_code == expected_status, resp.text
    assert not any(w.startswith("BREAK_WAIVER") for w in resp.json().get("warnings") or []), resp.text
    _db_session.expire_all()
    entry = _db_session.query(TimeEntry).one()
    assert (entry.uncredited_minutes, entry.net_hours) == (150, Decimal("7.50"))

