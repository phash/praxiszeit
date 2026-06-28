"""Fix #2: the employee PUT must not wipe raw_start/raw_end (§16) or re-clamp the
stored times on a non-time change (e.g. a note-only edit).

Before the fix, update_time_entry clamped entry.start/end unconditionally and wrote
raw_*=None on every update, so a reine Notiz-Änderung destroyed the §16 raw stamp
(and could lower Ist on a shifted soll window). The admin path already gated this.
"""
from datetime import time

from app.models import User, UserRole, TimeEntry
from app.routers.time_entries import update_time_entry, _today_local
from app.schemas.time_entry import TimeEntryUpdate
from tests.conftest import DEFAULT_TENANT_ID


def _user(db):
    u = User(
        username="fix2_emp", email="fix2@t.de", password_hash="h",
        first_name="F", last_name="L", role=UserRole.EMPLOYEE, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_note_only_update_preserves_raw_and_net(db, default_tenant):
    user = _user(db)
    entry = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        date=_today_local(),
        start_time=time(8, 0), end_time=time(16, 0),
        # §16: an earlier clamp recorded the raw (un-credited) stamp.
        raw_start_time=time(7, 0), raw_end_time=time(18, 0),
        break_minutes=30, note="alt",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    original_net = entry.net_hours

    update_time_entry(
        str(entry.id), TimeEntryUpdate(note="neue notiz"),
        db=db, current_user=user,
    )

    db.refresh(entry)
    assert entry.note == "neue notiz"
    # raw stamps survive a note-only edit
    assert entry.raw_start_time == time(7, 0)
    assert entry.raw_end_time == time(18, 0)
    # credited times + net hours unchanged
    assert entry.start_time == time(8, 0)
    assert entry.end_time == time(16, 0)
    assert entry.net_hours == original_net
