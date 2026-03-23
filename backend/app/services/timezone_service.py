"""Timezone helpers – all business logic should use these instead of date.today() or datetime.now()."""

from datetime import datetime, date
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Berlin")


def now_local() -> datetime:
    """Return current datetime in Europe/Berlin."""
    return datetime.now(LOCAL_TZ)


def today_local() -> date:
    """Return today's date in Europe/Berlin."""
    return now_local().date()
