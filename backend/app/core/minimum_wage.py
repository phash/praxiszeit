"""#377 Gesetzlicher Mindestlohn (§ 1 MiLoG) als datumsabhängige Konstante.

Quelle: Mindestlohnkommission / BMAS. NEUE Stufe chronologisch ergänzen, sobald
beschlossen — Werte NIE raten. Rein statisch (kein DB/Netz), darf `/system/info`
nie brechen.
"""
from datetime import date
from decimal import Decimal

# (Wirksam-ab, €/h), aufsteigend sortiert.
_MINIMUM_WAGE_STEPS = [
    (date(2025, 1, 1), Decimal("12.82")),
    (date(2026, 1, 1), Decimal("13.90")),
    (date(2027, 1, 1), Decimal("14.60")),
]


def minimum_wage_for(d: date) -> Decimal:
    """Gültiger gesetzlicher Mindestlohn (€/h) zum Datum d."""
    applicable = _MINIMUM_WAGE_STEPS[0][1]
    for eff, val in _MINIMUM_WAGE_STEPS:
        if d >= eff:
            applicable = val
    return applicable


def minimum_wage_info(today: date) -> dict:
    """{current, since, next|None} für die Anzeige (floats/ISO-Strings)."""
    current, since = _MINIMUM_WAGE_STEPS[0][1], _MINIMUM_WAGE_STEPS[0][0]
    nxt = None
    for eff, val in _MINIMUM_WAGE_STEPS:
        if today >= eff:
            current, since = val, eff
        elif nxt is None:
            nxt = {"value": float(val), "from": eff.isoformat()}
    return {"current": float(current), "since": since.isoformat(), "next": nxt}
