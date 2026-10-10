"""Spec 6.3: Falltabelle K1–K21 (Puffer 15 Min). Eine Quelle für Backend-Tests;
PR2 ergänzt die Spalte der ArbZG-Codes und spiegelt die IDs im Frontend-Test.

``clamp_text`` beschreibt, was ``clamp_warning_text`` für das Ergebnis EINES
clamp-Aufrufs liefert: None | "hull" | "collapse" | "gap" | "hull+gap" |
"in_gap" | "clock_in_gap". (K15 liefert beim Auto-Close keine Warnung — der
Auto-Close ruft clamp_warning nicht auf; K20 ist hier ein einziger Aufruf
07:00–18:00, beim echten Ausstempeln greift nur noch der Lückenteil.)
"""
from datetime import date, time
from typing import NamedTuple, Optional

from app.models import User, UserRole
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

EASTER_MONDAY = date(2026, 4, 6)   # Montag, Feiertag (Fixture legt ihn an)
SUNDAY = date(2026, 6, 7)
DEC24_THU = date(2026, 12, 24)     # Donnerstag; Fixture setzt dec24 = half_day

K6_BLOCKS = block_week(mon=[("08:00", "12:00"), ("12:30", "16:00")])
K17_BLOCKS = block_week(mon=[("07:00", "10:00"), ("11:00", "13:00"), ("16:00", "19:00")])
K18_BLOCKS = block_week(thu=[("08:00", "12:00"), ("15:00", "18:00")])
K19_BLOCKS = block_week(mon=[("08:00", "10:00"), ("15:00", "18:00")])


class KCase(NamedTuple):
    id: str
    blocks: list
    day: date
    start: time
    end: Optional[time]
    break_minutes: int
    track_hours: bool
    credit_override: bool
    auto_closed: bool
    exp_start: time
    exp_end: Optional[time]
    exp_raw_start: Optional[time]
    exp_raw_end: Optional[time]
    exp_uncredited: int
    exp_grace: Optional[int]
    exp_net: str
    exp_not_credited: int
    clamp_text: Optional[str]


def _t(h, m=0):
    return time(h, m)


K_CASES = [
    KCase("K1", K_BLOCKS, MON, _t(8), _t(18), 0, True, False, False, _t(8), _t(18), None, None, 150, 15, "7.50", 150, "gap"),
    KCase("K2", K_BLOCKS, MON, _t(13), None, 0, True, False, False, _t(13), None, None, None, 0, 15, "0.00", 0, "clock_in_gap"),
    KCase("K2b", K_BLOCKS, MON, _t(13), _t(18), 0, True, False, False, _t(13), _t(18), None, None, 105, 15, "3.25", 105, "gap"),
    KCase("K3", K_BLOCKS, MON, _t(12, 30), _t(14, 30), 0, True, False, False, _t(12, 30), _t(14, 30), None, None, 120, 15, "0.00", 120, "in_gap"),
    KCase("K4", K_BLOCKS, MON, _t(8), _t(12, 5), 0, True, False, False, _t(8), _t(12, 5), None, None, 0, 15, "4.08", 0, None),
    KCase("K5", K_BLOCKS, MON, _t(8), _t(12, 30), 0, True, False, False, _t(8), _t(12, 30), None, None, 15, 15, "4.25", 15, "gap"),
    KCase("K6", K6_BLOCKS, MON, _t(8), _t(16), 0, True, False, False, _t(8), _t(16), None, None, 0, 15, "8.00", 0, None),
    KCase("K7", K_BLOCKS, MON, _t(7), _t(19), 0, True, False, False, _t(7, 45), _t(18, 15), _t(7), _t(19), 150, 15, "8.00", 240, "hull+gap"),
    KCase("K8", K_BLOCKS, MON, _t(5), _t(7), 0, True, False, False, _t(5), _t(5), _t(5), _t(7), 0, 15, "0.00", 120, "collapse"),
    KCase("K9", K_BLOCKS, MON, _t(8), _t(18), 30, True, False, False, _t(8), _t(18), None, None, 150, 15, "7.00", 150, "gap"),
    KCase("K10", K_BLOCKS, MON, _t(8), _t(18), 45, True, True, False, _t(8), _t(18), None, None, 0, None, "9.25", 0, None),
    KCase("K11", K_BLOCKS, EASTER_MONDAY, _t(8), _t(18), 45, True, False, False, _t(8), _t(18), None, None, 0, None, "9.25", 0, None),
    KCase("K12", K_BLOCKS, SUNDAY, _t(8), _t(18), 45, True, False, False, _t(8), _t(18), None, None, 0, None, "9.25", 0, None),
    KCase("K13", K_BLOCKS, MON, _t(8), _t(18), 45, False, False, False, _t(8), _t(18), None, None, 0, None, "9.25", 0, None),
    KCase("K14", K_BLOCKS, MON, _t(8), None, 0, True, False, False, _t(8), None, None, None, 0, 15, "0.00", 0, None),
    KCase("K15", K_BLOCKS, MON, _t(8), _t(23, 59), 0, True, False, True, _t(8), _t(18, 15), None, _t(23, 59), 150, 15, "7.75", 150, "hull+gap"),
    KCase("K16", K_BLOCKS, MON, _t(14, 30), _t(18), 0, True, False, False, _t(14, 30), _t(18), None, None, 15, 15, "3.25", 15, "gap"),
    KCase("K17", K17_BLOCKS, MON, _t(7), _t(19), 0, True, False, False, _t(7), _t(19), None, None, 180, 15, "9.00", 180, "gap"),
    KCase("K18", K18_BLOCKS, DEC24_THU, _t(8), _t(18), 0, True, False, False, _t(8), _t(18), None, None, 150, 15, "7.50", 150, "gap"),
    KCase("K19", K19_BLOCKS, MON, _t(8), _t(18), 0, True, False, False, _t(8), _t(18), None, None, 270, 15, "5.50", 270, "gap"),
    KCase("K20", K_BLOCKS, MON, _t(7), _t(18), 0, True, False, False, _t(7, 45), _t(18), _t(7), None, 150, 15, "7.75", 195, "hull+gap"),
    KCase("K21", K_BLOCKS, MON, _t(8), _t(18), 45, True, False, False, _t(8), _t(18), None, None, 150, 15, "6.75", 150, "gap"),
]

# Spec 6.3, Spalte „Meldung" (PR2): Warncodes, die POST /api/time-entries/ —
# manuelles Anlegen durch die Person selbst, Falltag = heute — für den
# GESCHLOSSENEN Eintrag liefert. None = über diesen Pfad nicht erzeugbar
# (offen K2/K14, anerkannt K10 → Task 5, Auto-Close K15). K20 hier als ein
# Eintrag 07:00–18:00 (EARLY_START gibt es nur beim Einstempeln). K_HTTP_400 =
# harte §4-Sperre (K6). Der Frontend-Zwilling utils/workBlocksCases.ts führt
# dieselben IDs.
K_HTTP_400 = "HTTP_400"
_CLAMPED = "WORK_WINDOW_CLAMPED"
K_CODES: dict = {
    "K1": frozenset({_CLAMPED, "PRESENCE_BREAK"}),
    "K2": None,
    "K2b": frozenset({_CLAMPED}),
    "K3": frozenset({_CLAMPED}),
    "K4": frozenset(),
    "K5": frozenset({_CLAMPED}),
    "K6": frozenset({K_HTTP_400}),
    "K7": frozenset({_CLAMPED, "PRESENCE_DAILY_HOURS", "PRESENCE_BREAK"}),
    "K8": frozenset({_CLAMPED}),
    "K9": frozenset({_CLAMPED, "BREAK_IN_GAP", "PRESENCE_BREAK"}),
    "K10": None,
    "K11": frozenset({"HOLIDAY_WORK", "DAILY_HOURS_WARNING"}),
    "K12": frozenset({"SUNDAY_WORK", "DAILY_HOURS_WARNING"}),
    "K13": frozenset({"DAILY_HOURS_WARNING"}),
    "K14": None,
    "K15": None,
    "K16": frozenset({_CLAMPED}),
    "K17": frozenset({_CLAMPED, "DAILY_HOURS_WARNING", "PRESENCE_DAILY_HOURS", "PRESENCE_BREAK"}),
    "K18": frozenset({_CLAMPED, "PRESENCE_BREAK"}),
    "K19": frozenset({_CLAMPED, "PRESENCE_BREAK"}),
    "K20": frozenset({_CLAMPED, "PRESENCE_DAILY_HOURS", "PRESENCE_BREAK"}),
    "K21": frozenset({_CLAMPED, "BREAK_IN_GAP"}),
}
assert set(K_CODES) == {c.id for c in K_CASES}


def k_user(case: KCase) -> User:
    """Transiente Person ohne Verlauf → der Resolver nimmt ``work_blocks``."""
    return User(
        username=f"k_{case.id.lower()}", email=f"{case.id.lower()}@x.de", password_hash="h",
        first_name="K", last_name=case.id, role=UserRole.EMPLOYEE, weekly_hours=40.0,
        work_days_per_week=5, vacation_days=30, track_hours=case.track_hours,
        tenant_id=DEFAULT_TENANT_ID, work_blocks=case.blocks,
    )
