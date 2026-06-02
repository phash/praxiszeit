"""#201: Soll-Arbeitszeit-Fenster — kappt das Ist beim Schreiben.

Pro User je Wochentag (Mo–Fr) ein optionales Fenster [Soll-Beginn, Soll-Ende].
Gestempelte/eingetragene Zeit außerhalb von [Beginn − Puffer, Ende + Puffer]
wird gekappt; der Rohstempel wird separat bewahrt. Opt-in: NULL = keine Kappung.
"""
from datetime import date, time
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting

_WEEKDAY_ATTR = {
    0: ("scheduled_start_monday", "scheduled_end_monday"),
    1: ("scheduled_start_tuesday", "scheduled_end_tuesday"),
    2: ("scheduled_start_wednesday", "scheduled_end_wednesday"),
    3: ("scheduled_start_thursday", "scheduled_end_thursday"),
    4: ("scheduled_start_friday", "scheduled_end_friday"),
}

DEFAULT_GRACE_MINUTES = 15


def get_grace_minutes(db: Session, tenant_id) -> int:
    """work_window_grace_minutes aus system_settings (Default 15, >= 0)."""
    s = db.query(SystemSetting).filter(
        SystemSetting.key == "work_window_grace_minutes",
        SystemSetting.tenant_id == tenant_id,
    ).first()
    if not s:
        return DEFAULT_GRACE_MINUTES
    try:
        return max(0, int(s.value))
    except (TypeError, ValueError):
        return DEFAULT_GRACE_MINUTES


def get_scheduled_window(user, d: date) -> Tuple[Optional[time], Optional[time]]:
    attrs = _WEEKDAY_ATTR.get(d.weekday())
    if attrs is None:  # Wochenende
        return (None, None)
    return (getattr(user, attrs[0], None), getattr(user, attrs[1], None))


def _shift(t: time, minutes: int) -> time:
    """t um minutes verschieben, auf [00:00, 23:59] des Tages begrenzt."""
    total = t.hour * 60 + t.minute + minutes
    total = max(0, min(total, 23 * 60 + 59))
    return time(total // 60, total % 60)


def clamp(
    user, d: date, start: Optional[time], end: Optional[time], grace_minutes: int,
) -> Tuple[Optional[time], Optional[time], Optional[time], Optional[time]]:
    """Gibt (eff_start, eff_end, raw_start, raw_end) zurück. raw_* nur gesetzt,
    wenn die jeweilige Seite gekappt wurde. Übersprungen bei track_hours=False."""
    if not getattr(user, "track_hours", True):
        return (start, end, None, None)

    soll_start, soll_end = get_scheduled_window(user, d)
    eff_start, eff_end = start, end
    raw_start = raw_end = None

    if soll_start is not None and start is not None:
        floor = _shift(soll_start, -grace_minutes)
        if start < floor:
            eff_start, raw_start = floor, start

    if soll_end is not None and end is not None:
        ceil = _shift(soll_end, grace_minutes)
        if end > ceil:
            eff_end, raw_end = ceil, end

    # Schutz vor Inversion: liegt der Eintrag ganz außerhalb des Fensters,
    # würde Kappen eff_start >= eff_end erzeugen → NICHT kappen (Rohwerte behalten),
    # damit keine 0h-/invertierte Buchung entsteht und net_hours korrekt bleibt.
    if eff_start is not None and eff_end is not None and eff_start >= eff_end:
        return (start, end, None, None)
    return (eff_start, eff_end, raw_start, raw_end)
