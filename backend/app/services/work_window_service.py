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


# #462: Kennung der weichen Warnung. Format wie die uebrigen Warnungen des
# Projekts ("CODE: Text"), damit sie durch `showArbzgWarnings` laeuft.
CLAMP_WARNING_CODE = "WORK_WINDOW_CLAMPED"


def _hhmm(t: Optional[time]) -> str:
    return t.strftime("%H:%M") if t else "?"


def clamp_warning(
    raw_start: Optional[time], raw_end: Optional[time],
    eff_start: Optional[time], eff_end: Optional[time],
    grace_minutes: int,
) -> Optional[str]:
    """Text der Kappungs-Warnung — oder None, wenn nichts gekappt wurde.

    #462 (Kundenmeldung): Die Kappung ist gewollt (Anti-Abuse, #201), sie lief
    aber **stumm**. Ein Admin trug 07:37 ein, gespeichert wurde 07:45, und er
    erfuhr es nie — bei einer Zeiterfassung ist eine unbemerkte Aenderung
    fremder Arbeitszeit das eigentliche Problem, nicht die Kappung. Der Melder
    hielt das fuer eine Viertelstunden-Rundung; die entsteht dadurch, dass
    ``soll_start`` meist auf einer vollen Stunde liegt und der Puffer 15 Minuten
    betraegt.

    DIE eine Quelle des Textes: ``clamp`` wird an elf Stellen aufgerufen
    (Stempeln, manuelles Anlegen/Bearbeiten in beiden Rollen, Genehmigung eines
    Aenderungsantrags, XLS-Import). Ein zweiter Nachbau je Aufrufer waere genau
    das Muster, das in diesem Projekt schon mehrfach auseinandergelaufen ist.
    """
    teile = []
    if raw_start is not None and eff_start is not None:
        teile.append(f"Beginn {_hhmm(raw_start)} \u2192 {_hhmm(eff_start)}")
    if raw_end is not None and eff_end is not None:
        teile.append(f"Ende {_hhmm(raw_end)} \u2192 {_hhmm(eff_end)}")
    if not teile:
        return None
    return (
        f"{CLAMP_WARNING_CODE}: Die eingetragene Zeit wurde auf das hinterlegte "
        f"Arbeitszeit-Fenster gekappt ({', '.join(teile)}; Puffer {grace_minutes} "
        f"Minuten). Angerechnet wird die gekappte Zeit; die urspruengliche "
        f"Eingabe bleibt als Rohstempel gespeichert."
    )


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

    # Komplett außerhalb des Fensters: liegt der Eintrag ganz vor
    # [Soll-Beginn − Puffer] bzw. ganz hinter [Soll-Ende + Puffer], würde die
    # Kappung eff_start >= eff_end erzeugen. #201-Design-Spec §5: dann werden
    # **0 Stunden angerechnet**, der Rohstempel bleibt aber erhalten (§16) — sonst
    # ließe sich Arbeitszeit außerhalb des Soll-Fensters „erarbeiten" (Anti-Abuse,
    # die Motivation des Features). Die angerechnete (effektive) Zeit kollabiert
    # deshalb auf einen Punkt (= ``start``) → ``TimeEntry.net_hours`` floored auf 0.
    # Punkt = ``start``, damit auch ``clock_out`` (setzt nur ``end_time = eff_end``,
    # ``start_time`` bleibt der Stempel) net_hours == 0 erhält. Beide Original-
    # stempel werden in raw_start/raw_end bewahrt — die §5-Ruhezeitprüfung rechnet
    # weiterhin gegen diese Rohstempel (``raw_* or <gekappt>``).
    if eff_start is not None and eff_end is not None and eff_start >= eff_end:
        return (start, start, start, end)
    return (eff_start, eff_end, raw_start, raw_end)
