"""
ArbZG utility functions shared across routers and services.
"""
from datetime import time
from typing import Optional

# §2 Abs. 4 ArbZG: mindestens 2 Stunden Nachtzeit = Nachtarbeit
NIGHT_THRESHOLD_MINUTES = 120


def is_night_work(start_time: Optional[time], end_time: Optional[time]) -> bool:
    """
    Gibt True zurück wenn >2h Nachtzeit (23:00–06:00) überschnitten werden (§2 Abs. 4 / §6 ArbZG).
    Returns False if either argument is None.
    """
    if not start_time or not end_time:
        return False

    def to_min(t: time) -> int:
        return t.hour * 60 + t.minute

    s = to_min(start_time)
    e = to_min(end_time)
    if e <= s:  # Mitternachtsübergang
        e += 1440

    # Nachtzeit-Segmente in Minuten seit Tagesbeginn:
    # 0–360 = 00:00–06:00, 1380–1440 = 23:00–24:00, 1440–1800 = 00:00–06:00 (Folgetag)
    night_minutes = (
        max(0, min(e, 360) - max(s, 0))        # 00:00–06:00
        + max(0, min(e, 1440) - max(s, 1380))  # 23:00–24:00
        + max(0, min(e, 1800) - max(s, 1440))  # 00:00–06:00 (nach Mitternacht)
    )
    return night_minutes > NIGHT_THRESHOLD_MINUTES
