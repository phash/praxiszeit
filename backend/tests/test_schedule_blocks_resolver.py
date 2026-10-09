"""Spec 3.3/3.6: Blöcke kommen datumsaufgelöst aus dem Vertrags-Snapshot."""
from datetime import date, time

from app.models import ChangeRequest, TimeEntry, WorkingHoursChange
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week, legacy_week


def _row(db, user, effective_from, blocks):
    row = WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=effective_from,
        weekly_hours=40.0, use_daily_schedule=False, work_days_per_week=5, blocks=blocks,
    )
    db.add(row)
    db.commit()
    return row


def test_fallback_to_user_work_blocks_without_history(db, test_user):
    test_user.work_blocks = legacy_week(mon=("07:30", "16:30"))
    db.commit()
    s = cs.get_schedule_for_date(db, test_user, MON)
    assert s.blocks[0] == ((450, 990),)
    assert s.block_pauses == (None,) * 5


def test_null_in_history_row_means_no_blocks_never_fallback(db, test_user):
    test_user.work_blocks = legacy_week(mon=("07:30", "16:30"))
    _row(db, test_user, date(2026, 1, 1), None)
    s = cs.get_schedule_for_date(db, test_user, MON)
    assert s.blocks is None and s.block_pauses is None


def test_history_row_wins_and_date_before_falls_back(db, test_user):
    test_user.work_blocks = legacy_week(mon=("07:30", "16:30"))
    _row(db, test_user, date(2026, 5, 1), K_BLOCKS)
    assert cs.get_schedule_for_date(db, test_user, MON).blocks[0] == ((480, 720), (900, 1080))
    assert cs.get_schedule_for_date(db, test_user, date(2026, 4, 27)).blocks[0] == ((450, 990),)


def test_five_empty_days_normalise_to_none(db, test_user):
    _row(db, test_user, date(2026, 1, 1), block_week())
    assert cs.get_schedule_for_date(db, test_user, MON).blocks is None


def test_preload_path_matches_query_path(db, test_user):
    _row(db, test_user, date(2026, 5, 1), K_BLOCKS)
    rows = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).all()
    assert cs.get_schedule_for_date(db, test_user, MON, rows) == cs.get_schedule_for_date(db, test_user, MON)


def test_parse_cache_is_invalidated_by_reassignment(db, test_user):
    row = _row(db, test_user, date(2026, 5, 1), K_BLOCKS)
    first = cs.get_schedule_for_date(db, test_user, MON, [row]).blocks
    assert cs.get_schedule_for_date(db, test_user, MON, [row]).blocks is first   # Cache
    row.blocks = legacy_week(mon=("09:00", "17:00"))                            # Neuzuweisung
    assert cs.get_schedule_for_date(db, test_user, MON, [row]).blocks[0] == ((540, 1020),)


def test_get_blocks_json_for_date_round_trip(db, test_user):
    _row(db, test_user, date(2026, 5, 1), K_BLOCKS)
    assert cs.get_blocks_json_for_date(db, test_user, MON) == K_BLOCKS
    assert cs.get_blocks_json_for_date(db, test_user, date(2026, 4, 27)) is None


def test_new_time_entry_and_cr_columns_have_defaults(db, test_user):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                  start_time=time(8, 0), end_time=time(9, 0), break_minutes=0)
    cr = ChangeRequest(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id,
                       request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
                       reason="x")
    db.add_all([e, cr])
    db.commit()
    db.refresh(e)
    db.refresh(cr)
    assert (e.uncredited_minutes, e.credit_override, e.auto_closed, e.clamp_grace_minutes) == (0, False, False, None)
    assert (cr.request_credit_override, cr.original_uncredited_minutes) == (False, None)
