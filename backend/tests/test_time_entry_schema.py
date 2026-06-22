"""Regression tests for the TimeEntry request schemas.

Issue #225: editing a time entry failed with HTTP 422 "Input should be None".
Root cause: in ``TimeEntryUpdate`` the field is literally named ``date`` AND its
type is ``date`` (``from datetime import date``). With a ``= None`` default,
Pydantic 2.13's annotation resolution sees ``date`` bound to ``None`` in the
class namespace, so ``Optional[date]`` collapses to ``Optional[None]`` ==
``NoneType`` → every non-null date is rejected with ``none_required``.

The frontend always sends ``date`` in the update body, so every edit broke;
create worked because ``TimeEntryCreate.date`` has no default (no shadowing).
"""

from datetime import date as _date

from app.schemas.time_entry import (
    TimeEntryBase,
    TimeEntryCreate,
    TimeEntryResponse,
    TimeEntryUpdate,
)


def test_update_date_annotation_is_not_nonetype():
    """The resolved field type must be the date type, never NoneType."""
    assert TimeEntryUpdate.model_fields["date"].annotation is not type(None)


def test_update_accepts_a_real_date_string():
    """#225: a normal edit (date present) must validate, not raise none_required."""
    m = TimeEntryUpdate(
        date="2026-06-22",
        start_time="08:15",
        end_time="10:53",
        break_minutes=0,
        note="",
    )
    assert m.date == _date(2026, 6, 22)
    assert m.start_time.hour == 8 and m.end_time.hour == 10


def test_update_date_still_optional():
    """Partial updates without a date must remain valid (field stays optional)."""
    m = TimeEntryUpdate(start_time="09:00", end_time="17:00")
    assert m.date is None


def test_create_and_response_date_roundtrip():
    """Create/Response date fields keep working (no regression)."""
    c = TimeEntryCreate(date="2026-06-22", start_time="08:00", end_time="16:00")
    assert c.date == _date(2026, 6, 22)
    assert TimeEntryBase.model_fields["date"].annotation is _date
    assert TimeEntryResponse.model_fields["date"].annotation is _date
