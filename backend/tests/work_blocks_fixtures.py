"""Test-Helfer: kanonische JSON-Form der Arbeitszeit-Blöcke (Spec 3.1)."""
from datetime import date

_DAYS = ("mon", "tue", "wed", "thu", "fri")

# 2026-06-01 ist ein Montag; die Falltabelle K1–K21 (Spec 6.3) rechnet darauf.
MON = date(2026, 6, 1)


def legacy_week(**days):
    """Altfenster wie nach Migration 073: je Tag höchstens EIN Block,
    ``pause_minutes`` None. ``mon=("08:00", "17:00")``; halboffen
    ``("08:00", None)`` → Ende ``23:59``, ``(None, "17:00")`` → Beginn
    ``00:00`` (Platzhalter wie Spec 5.3)."""
    unknown = set(days) - set(_DAYS)
    if unknown:
        raise TypeError(f"unbekannte Wochentage: {sorted(unknown)}")
    week = []
    for key in _DAYS:
        window = days.get(key)
        if window is None:
            week.append({"blocks": [], "pause_minutes": None})
            continue
        start, end = window
        week.append({
            "blocks": [{"start": start or "00:00", "end": end or "23:59"}],
            "pause_minutes": None,
        })
    return week


def block_week(pause: int = 0, **days):
    """Neue Blöcke (``pause_minutes`` int): ``mon=[("08:00", "12:00"), ("15:00", "18:00")]``.
    Tage ohne Blöcke tragen ``pause_minutes`` 0 (Spec 3.4)."""
    unknown = set(days) - set(_DAYS)
    if unknown:
        raise TypeError(f"unbekannte Wochentage: {sorted(unknown)}")
    week = []
    for key in _DAYS:
        blocks = days.get(key) or []
        week.append({
            "blocks": [{"start": s, "end": e} for s, e in blocks],
            "pause_minutes": pause if blocks else 0,
        })
    return week


# Spec 6.3: Mo 08:00–12:00 + 15:00–18:00, Pause 0 → Hülle 07:45–18:15, Lücke 12:15–14:45.
K_BLOCKS = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")])
