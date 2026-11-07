"""Timezone helpers – all business logic should use these instead of date.today() or datetime.now()."""

from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Berlin")


def now_local() -> datetime:
    """Return current datetime in Europe/Berlin."""
    return datetime.now(LOCAL_TZ)


def today_local() -> date:
    """Return today's date in Europe/Berlin."""
    return now_local().date()


def hours_between(d1: date, t1: time, d2: date, t2: time) -> float:
    """Tatsächlich verstrichene Stunden zwischen zwei Ortszeiten (Europe/Berlin).

    #540 (A1-10): ``datetime``-Subtraktion zweier Werte mit DEMSELBEN
    ``tzinfo``-Objekt rechnet Python naiv in Wanduhrzeit — der frühere „Fix"
    F-030 (beide tz-aware kombinieren) änderte daran nichts: Sa 20:00 → So
    07:00 über die Umstellung auf Sommerzeit ergab 11,0 h statt 10,0 h (§5 wurde
    übersehen), im Oktober 1 h zu wenig (Fehlalarm). Über UTC gerechnet stimmt
    die Dauer. Mehrdeutige Uhrzeiten (Oktober, 02:00–03:00) gelten als die
    erste (``fold=0``)."""
    a = datetime.combine(d1, t1, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    b = datetime.combine(d2, t2, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    return (b - a).total_seconds() / 3600
