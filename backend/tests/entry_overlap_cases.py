"""#538 (A1-02): Falltabelle der Überschneidungsregel — EINE Quelle für die
Backend-Tests; ``frontend/src/utils/entryOverlapCases.ts`` führt dieselben IDs
und Werte (``entryOverlap.test.ts``). Zeiten = Anwesenheit laut Stempel.

``a``/``b``: (Beginn, Ende) als "HH:MM"; Ende ``None`` = laufender Eintrag
(heute bis ``now``, an einem früheren Tag bis Tagesende — ``a_past_day``).
"""
from typing import NamedTuple, Optional


class OCase(NamedTuple):
    id: str
    a: tuple
    b: tuple
    now: str
    a_past_day: bool
    overlap: bool


O_CASES = [
    OCase("O1", ("08:00", "12:00"), ("12:00", "13:00"), "18:00", False, False),  # stößt an
    OCase("O2", ("08:00", "12:00"), ("11:59", "13:00"), "18:00", False, True),
    OCase("O3", ("08:00", "12:00"), ("09:00", "10:00"), "18:00", False, True),   # enthalten
    OCase("O4", ("08:00", "12:00"), ("07:00", "08:00"), "18:00", False, False),  # stößt davor an
    OCase("O5", ("10:00", "10:00"), ("09:00", "11:00"), "18:00", False, True),   # Eintrag ohne Dauer
    OCase("O6", ("08:00", None), ("09:30", "09:45"), "10:00", False, True),      # laufend bis jetzt
    OCase("O7", ("08:00", None), ("10:00", "11:00"), "10:00", False, False),     # stößt an „jetzt" an
    OCase("O8", ("08:00", None), ("20:00", "21:00"), "10:00", True, True),       # früherer Tag: bis 24:00
    OCase("O9", ("08:00", "12:00"), ("12:00", None), "12:00", False, False),     # Einstempeln am Ende
    OCase("O10", ("08:00", "12:00"), ("11:59", None), "11:59", False, True),     # Einstempeln mittendrin
]

# Hinweistexte (wortgleich zum Frontend ``overlapMessage``).
MSG_CLOSED = (
    "Überschneidung mit dem Eintrag 08:00–12:00 am 02.06.2026: Zeiteinträge einer "
    "Person dürfen sich nicht überschneiden. Bitte die Zeiten anpassen oder den "
    "vorhandenen Eintrag bearbeiten."
)
MSG_RUNNING = (
    "Überschneidung mit dem laufenden Eintrag ab 08:00 am 02.06.2026: Zeiteinträge "
    "einer Person dürfen sich nicht überschneiden. Bitte die Zeiten anpassen oder den "
    "vorhandenen Eintrag bearbeiten."
)


def hm(s: Optional[str]):
    from datetime import time
    if s is None:
        return None
    h, m = s.split(":")
    return time(int(h), int(m))
