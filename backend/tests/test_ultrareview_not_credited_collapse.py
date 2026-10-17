"""Ultrareview: „nicht angerechnet" darf die Anwesenheit nicht übersteigen.

Einstempeln 05:00 vor der Hülle (07:45) speichert den Beginn 07:45 mit
Rohstempel 05:00; Ausstempeln 06:00 liegt ebenfalls vor der Hülle → Kollaps auf
den gespeicherten Beginn: 07:45–07:45, Rohstempel 05:00–06:00. Die Hüllen-
Startseite rechnete ``eff_start − raw_start`` = 165 Min., anwesend war die
Person aber nur 60 Min. Der Hüllen-Anteil endet am Rohende.

Wortgleiche Fälle im Frontend-Zwilling: ``frontend/src/utils/workBlocks.test.ts``
(„notCreditedMinutes — Kollaps nach gekapptem Beginn").
"""
from datetime import time

import pytest

from app.models import TimeEntry
from app.services import work_window_service as wws
from tests.work_blocks_cases import K_CASES, k_user
from tests.work_blocks_fixtures import MON

# (id, start, end, raw_start, raw_end, uncredited, auto_closed, erwartet)
CASES = [
    ("N1", time(7, 45), time(7, 45), time(5), time(6), 0, False, 60),
    ("N2", time(7, 45), time(7, 45), time(7), time(7, 30), 0, False, 30),
    ("N3", time(7, 45), time(18, 15), time(7), time(19), 150, False, 240),
    ("N4", time(19), time(19), None, time(20), 0, False, 60),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_not_credited_bounded_by_raw_span(case):
    _id, s, e, rs, re_, unc, ac, exp = case
    entry = TimeEntry(start_time=s, end_time=e, raw_start_time=rs, raw_end_time=re_,
                      uncredited_minutes=unc, auto_closed=ac, break_minutes=0)
    assert wws.not_credited_minutes(entry) == exp


def test_clock_out_collapse_stores_this_shape(db, default_tenant):
    """So entsteht N1: ``clock_out`` kappt mit dem GESPEICHERTEN Beginn 07:45 und
    schreibt nur Ende + Rohende (der Rohbeginn 05:00 bleibt vom Einstempeln)."""
    user = k_user(K_CASES[0])
    r_in = wws.clamp(db, user, MON, time(5), None, 15, credit_override=False)
    assert (r_in.eff_start, r_in.raw_start) == (time(7, 45), time(5))
    r_out = wws.clamp(db, user, MON, r_in.eff_start, time(6), 15, credit_override=False)
    assert (r_out.eff_end, r_out.raw_end) == (time(7, 45), time(6))
