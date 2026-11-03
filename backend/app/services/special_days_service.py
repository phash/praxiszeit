"""Service for the configurable special days 24.12. and 31.12. (#146).

Each of the two dates can independently be configured per practice
(tenant-scoped, stored in ``system_settings``) as one of four modes:

- ``working_day`` (default, fully backward compatible — today both days are
  treated like any normal working day, no special handling at all),
- ``half_day``   (the daily target on that date is halved), or
- ``free``       (the daily target on that date is 0, like a public holiday), or
- ``max_hours``  (verkürzter Tag: the daily target is ``min(target, X)``).

Additionally, arbitrary dates can be reduced days (table ``reduced_days``,
mode ``max_hours`` as well); they are merged into the same config.

When a day is ``free`` it additionally carries a ``counts_as_vacation`` flag:

- ``counts_as_vacation = False`` → **bezahlte Freistellung** (paid leave): the
  target drops to 0 and NOTHING is deducted from the vacation budget. This is
  fully handled by the target reduction alone.
- ``counts_as_vacation = True``  → **Urlaub** (vacation): the target drops to 0
  AND the day consumes one vacation day. The deduction is applied
  non-invasively in ``calculation_service.get_vacation_account`` — no Absence
  rows are generated (see ``vacation_deduction_days_for_year``).

Settings (per tenant, in ``system_settings``):

- ``special_day_dec24_mode``                 ∈ {working_day, half_day, free, max_hours}
- ``special_day_dec24_max_hours``            hours X (only meaningful for max_hours)
- ``special_day_dec24_counts_as_vacation``   bool (only meaningful when free)
- ``special_day_dec31_mode``                 ∈ {working_day, half_day, free, max_hours}
- ``special_day_dec31_max_hours``            hours X (only meaningful for max_hours)
- ``special_day_dec31_counts_as_vacation``   bool (only meaningful when free)

The existing ``system_setting`` key/value store is reused, mirroring the
``holiday_state`` setting pattern.
"""

from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.public_holiday import PublicHoliday
from app.models.reduced_day import ReducedDay
from app.models.system_setting import SystemSetting

# Valid modes for a special day.
MODE_WORKING_DAY = "working_day"
MODE_HALF_DAY = "half_day"
MODE_FREE = "free"
MODE_MAX_HOURS = "max_hours"
VALID_MODES = {MODE_WORKING_DAY, MODE_HALF_DAY, MODE_FREE, MODE_MAX_HOURS}

DEFAULT_MAX_HOURS = Decimal("4")
MIN_MAX_HOURS = Decimal("0.25")
MAX_MAX_HOURS = Decimal("12")
MAX_HOURS_ERROR = "Die Stundenzahl muss zwischen 0,25 und 12 liegen (in Schritten von 0,25)."

_LABELS = {(12, 24): "Heiligabend", (12, 31): "Silvester"}

# (month, day) of the two configurable special days and their setting prefixes.
# Order matters only for readability; lookups are keyed by (month, day).
_SPECIAL_DAYS = {
    (12, 24): "special_day_dec24",
    (12, 31): "special_day_dec31",
}

# All setting keys this feature owns — used by the admin router whitelist.
SETTING_KEYS = {
    "special_day_dec24_mode",
    "special_day_dec24_counts_as_vacation",
    "special_day_dec31_mode",
    "special_day_dec31_counts_as_vacation",
    "special_day_dec24_max_hours",
    "special_day_dec31_max_hours",
}

MAX_HOURS_KEYS = {"special_day_dec24_max_hours", "special_day_dec31_max_hours"}

MODE_KEYS = {"special_day_dec24_mode", "special_day_dec31_mode"}
VACATION_FLAG_KEYS = {
    "special_day_dec24_counts_as_vacation",
    "special_day_dec31_counts_as_vacation",
}


def _get_raw_setting(db: Session, key: str, tenant_id, default: str) -> str:
    """Read a single tenant-scoped value from ``system_settings``.

    Mirrors ``holiday_service.get_holiday_state`` / ``settings_service.get_setting``.
    """
    # SEC-F: always scope by tenant_id. All callers pass a real tenant_id, and
    # leaving the filter conditional risked leaking another tenant's setting if
    # a None ever slipped through. Mirrors the unconditional filter in
    # get_special_day_state below.
    q = db.query(SystemSetting).filter(
        SystemSetting.key == key,
        SystemSetting.tenant_id == tenant_id,
    )
    s = q.first()
    return s.value if s else default


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def parse_max_hours(value) -> Decimal:
    """Strikt: Wert auf 0,01 quantisiert; ValueError(MAX_HOURS_ERROR) sonst."""
    try:
        d = Decimal(str(value).strip())
    except Exception:
        raise ValueError(MAX_HOURS_ERROR)
    if not d.is_finite() or d < MIN_MAX_HOURS or d > MAX_MAX_HOURS:
        raise ValueError(MAX_HOURS_ERROR)
    if d % MIN_MAX_HOURS != 0:
        raise ValueError(MAX_HOURS_ERROR)
    return d.quantize(Decimal("0.01"))


def _lenient_max_hours(value) -> Decimal:
    """Lesepfad: ungültig oder fehlend -> DEFAULT_MAX_HOURS."""
    if value is None:
        return DEFAULT_MAX_HOURS
    try:
        return parse_max_hours(value)
    except ValueError:
        return DEFAULT_MAX_HOURS


def get_special_day_settings(db: Session, tenant_id) -> Dict[str, object]:
    """Return the six special-day settings for a tenant (with defaults).

    Used by the admin router to expose the current configuration to the UI.
    """
    return {
        "special_day_dec24_mode": _get_raw_setting(
            db, "special_day_dec24_mode", tenant_id, MODE_WORKING_DAY
        ),
        "special_day_dec24_counts_as_vacation": _parse_bool(
            _get_raw_setting(
                db, "special_day_dec24_counts_as_vacation", tenant_id, "true"
            )
        ),
        "special_day_dec31_mode": _get_raw_setting(
            db, "special_day_dec31_mode", tenant_id, MODE_WORKING_DAY
        ),
        "special_day_dec31_counts_as_vacation": _parse_bool(
            _get_raw_setting(
                db, "special_day_dec31_counts_as_vacation", tenant_id, "true"
            )
        ),
        "special_day_dec24_max_hours": float(_lenient_max_hours(
            _get_raw_setting(db, "special_day_dec24_max_hours", tenant_id, "")
            or None
        )),
        "special_day_dec31_max_hours": float(_lenient_max_hours(
            _get_raw_setting(db, "special_day_dec31_max_hours", tenant_id, "")
            or None
        )),
    }


def get_special_day_config(db: Session, tenant_id, year: int) -> Dict[date, Dict[str, object]]:
    """Resolve the special-day configuration to concrete dates for ``year``.

    Each value is ``{"mode", "counts_as_vacation", "max_hours", "label"}``;
    ``max_hours`` (Decimal) is set only for mode ``max_hours``. 24./31.12. are
    always included (``working_day`` when unconfigured) so callers can tell
    "not configured" (date absent) from "explicitly a normal working day".
    All ``ReducedDay`` rows of the tenant in ``year`` are added as
    ``max_hours`` entries; a settings entry on 24./31.12. wins over a stray row.

    Two queries per call (settings + reduced days), both tenant-filtered.
    """
    rows = (
        db.query(SystemSetting)
        .filter(
            SystemSetting.tenant_id == tenant_id,
            SystemSetting.key.in_(SETTING_KEYS),
        )
        .all()
    )
    raw = {r.key: r.value for r in rows}

    config: Dict[date, Dict[str, object]] = {}
    for (month, day), prefix in _SPECIAL_DAYS.items():
        mode = raw.get(f"{prefix}_mode", MODE_WORKING_DAY)
        if mode not in VALID_MODES:
            mode = MODE_WORKING_DAY
        counts_as_vacation = _parse_bool(
            raw.get(f"{prefix}_counts_as_vacation", "true")
        )
        config[date(year, month, day)] = {
            "mode": mode,
            "counts_as_vacation": counts_as_vacation,
            "max_hours": (
                _lenient_max_hours(raw.get(f"{prefix}_max_hours"))
                if mode == MODE_MAX_HOURS else None
            ),
            "label": _LABELS[(month, day)],
        }

    reduced = (
        db.query(ReducedDay)
        .filter(
            ReducedDay.tenant_id == tenant_id,
            ReducedDay.date >= date(year, 1, 1),
            ReducedDay.date <= date(year, 12, 31),
        )
        .all()
    )
    for r in reduced:
        if r.date in config:
            continue
        config[r.date] = {
            "mode": MODE_MAX_HOURS,
            "counts_as_vacation": False,
            "max_hours": Decimal(str(r.max_hours)),
            "label": r.label,
        }
    return config


def configs_for_years(db: Session, tenant_id, years) -> Dict[int, dict]:
    """Eine Config je distinktem Jahr."""
    return {y: get_special_day_config(db, tenant_id, y) for y in set(years)}


def special_day_mode(target_date: date, config: Dict[date, Dict[str, object]]) -> Optional[str]:
    """Modus des Tages oder None, wenn kein Eintrag existiert."""
    entry = config.get(target_date)
    return entry["mode"] if entry is not None else None


def special_day_target(target_date: date, daily_target: Decimal, config: Dict[date, Dict[str, object]]) -> Decimal:
    """Tagessoll nach Sondertag-/Verkürzungsregel (die EINE Stelle für Soll-Schleifen)."""
    entry = config.get(target_date)
    if entry is None:
        return daily_target
    mode = entry["mode"]
    if mode == MODE_HALF_DAY:
        return daily_target * Decimal("0.5")
    if mode == MODE_FREE:
        return Decimal("0")
    if mode == MODE_MAX_HOURS and entry.get("max_hours") is not None:
        return min(daily_target, Decimal(str(entry["max_hours"])))
    return daily_target


def format_hours_de(h: Decimal) -> str:
    """4 -> '4', 4.5 -> '4,5', 4.25 -> '4,25'."""
    text = format(Decimal(str(h)).quantize(Decimal("0.01")), "f")
    text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def reduced_day_label(max_hours: Decimal) -> str:
    return f"verkürzter Tag (max. {format_hours_de(max_hours)} h)"


def day_label(target_date: date, config: Dict[date, Dict[str, object]]) -> Optional[str]:
    """„verkürzter Tag (max. X h)" für einen ``max_hours``-Tag, sonst None."""
    entry = config.get(target_date)
    if entry is None or entry["mode"] != MODE_MAX_HOURS or entry.get("max_hours") is None:
        return None
    return reduced_day_label(Decimal(str(entry["max_hours"])))


def list_reduced_days_public(db: Session, tenant_id) -> List[dict]:
    """Verkürzte Tage des Mandanten für den öffentlichen /api/settings-Kalender."""
    rows = (
        db.query(ReducedDay)
        .filter(ReducedDay.tenant_id == tenant_id)
        .order_by(ReducedDay.date)
        .all()
    )
    return [
        {"date": r.date.isoformat(), "label": r.label, "max_hours": float(r.max_hours)}
        for r in rows
    ]


def special_day_target_factor(
    target_date: date,
    config: Dict[date, Dict[str, object]],
) -> Optional[Decimal]:
    """Return the target multiplier a special-day rule imposes on ``target_date``.

    - ``None``           → no special-day rule applies (treat the day normally).
    - ``Decimal('0.5')`` → ``half_day``: the daily target is halved.
    - ``Decimal('0')``   → ``free``: the daily target is 0 (like a holiday).
    - ``None`` also for ``max_hours`` (kein fester Faktor; siehe
      :func:`special_day_target`).

    ``config`` must be the dict returned by :func:`get_special_day_config` for
    the relevant year. The caller is responsible for first handling weekends
    and existing holidays/absences — those already reduce the target to 0, so
    this function must NOT be consulted for them (avoids double-handling).
    """
    entry = config.get(target_date)
    if entry is None:
        return None
    mode = entry["mode"]
    if mode == MODE_HALF_DAY:
        return Decimal("0.5")
    if mode == MODE_FREE:
        return Decimal("0")
    return None


def vacation_deduction_dates_for_year(
    db: Session,
    tenant_id,
    year: int,
    holiday_dates: set,
) -> set:
    """Dates in ``year`` that are configured as ``free`` + ``counts_as_vacation``.

    These dates each consume one vacation day in
    ``calculation_service.get_vacation_account``. Weekends and existing public
    holidays are excluded (a free day that already is a holiday / weekend does
    not cost vacation — the employee wouldn't have worked anyway).

    ``holiday_dates`` is the set of the tenant's public-holiday dates the
    caller already loaded for the year, passed in to avoid a duplicate query.
    """
    config = get_special_day_config(db, tenant_id, year)
    result = set()
    for d, entry in config.items():
        if entry["mode"] != MODE_FREE:
            continue
        if not entry["counts_as_vacation"]:
            continue
        if d.weekday() >= 5:  # weekend — no work expected, no vacation cost
            continue
        if d in holiday_dates:  # already a holiday — no vacation cost
            continue
        result.add(d)
    return result


def free_special_days_in_range(db: Session, tenant_id, start: date, end: date) -> set:
    """Alle als ``free`` konfigurierten Sondertage (24./31.12.) im Bereich [start, end].

    AC-11: Diese Tage sind soll-frei (Tagessoll 0) → sie sind KEINE Arbeitstage und
    dürfen daher keine Betriebsferien-/Urlaubs-Absence bekommen (sonst kostete ein
    ohnehin freier Tag fälschlich einen Urlaubstag und reduzierte das Soll doppelt).
    ``free`` + ``counts_as_vacation``-Tage werden separat in get_vacation_account
    gezählt (vacation_deduction_dates) → der Ausschluss hier bleibt budget-neutral.
    (``half_day``-Sondertage sind KEINE freien Tage und werden NICHT ausgeschlossen;
    ihre 0,5-Kosten kommen seit #394 über den ``special_day_target_factor`` in
    get_vacation_account/absence_days + die Betriebsferien-Buchung.)
    """
    result = set()
    for year in range(start.year, end.year + 1):
        config = get_special_day_config(db, tenant_id, year)
        for d, entry in config.items():
            if entry["mode"] == MODE_FREE and start <= d <= end:
                result.add(d)
    return result


DayState = Tuple[str, Optional[bool], Optional[Decimal]]
_WORKING_STATE: DayState = (MODE_WORKING_DAY, None, None)


def _effective_state(settings: Dict[str, object], prefix: str) -> DayState:
    """Wirksamer Zustand eines Sondertags: (Modus, Urlaubs-Schalter, Stunden).
    Der Schalter zählt nur bei ``free``, die Stunden nur bei ``max_hours``."""
    mode = settings.get(f"{prefix}_mode", MODE_WORKING_DAY)
    if mode not in VALID_MODES:
        mode = MODE_WORKING_DAY
    cav = settings.get(f"{prefix}_counts_as_vacation") if mode == MODE_FREE else None
    hours = None
    if mode == MODE_MAX_HOURS:
        hours = _lenient_max_hours(settings.get(f"{prefix}_max_hours"))
    return mode, cav, hours


def setting_states(settings: Dict[str, object], years) -> Dict[date, DayState]:
    """Zustände des 24./31.12. in ``years`` aus Einstellungen (Format von
    :func:`get_special_day_settings`)."""
    return {
        date(y, m, d): _effective_state(settings, prefix)
        for y in years for (m, d), prefix in _SPECIAL_DAYS.items()
    }


def reduced_day_states(rows: Iterable[Tuple[date, Decimal]]) -> Dict[date, DayState]:
    return {
        d: (MODE_MAX_HOURS, None, Decimal(str(h)).quantize(Decimal("0.01")))
        for d, h in rows
    }


def changed_dates(before: Dict[date, DayState], after: Dict[date, DayState]) -> Set[date]:
    """Tage, deren Zustand sich unterscheidet (fehlend = Arbeitstag)."""
    return {
        d for d in set(before) | set(after)
        if before.get(d, _WORKING_STATE) != after.get(d, _WORKING_STATE)
    }


def free_state_changed_dates(
    before_states: Dict[date, DayState],
    after_states: Dict[date, DayState],
) -> Set[date]:
    """Tage, die durch den Wechsel zu „frei" werden oder es nicht mehr sind
    (Gesamtreview 1.20) — nur dort ändert sich, ob gegen die Arbeitszeit-Blöcke
    gekappt wird (E35/#484)."""
    return {
        d for d in set(before_states) | set(after_states)
        if (before_states.get(d, _WORKING_STATE)[0] == MODE_FREE)
        != (after_states.get(d, _WORKING_STATE)[0] == MODE_FREE)
    }


def years_affected_by_change(
    db: Session,
    tenant_id,
    before_states: Dict[date, DayState],
    after_states: Dict[date, DayState],
) -> List[int]:
    """Jahre der geänderten Tage, an denen sich Soll, Gutschrift oder
    Urlaubsverbrauch tatsächlich ändert: nur Werktage ohne Feiertag des
    Mandanten zählen (an Wochenenden/Feiertagen wird der Tag nicht ausgewertet)."""
    candidates = {
        d for d in changed_dates(before_states, after_states) if d.weekday() < 5
    }
    if not candidates:
        return []
    holidays = {
        r[0]
        for r in db.query(PublicHoliday.date).filter(
            PublicHoliday.tenant_id == tenant_id,
            PublicHoliday.date.in_(candidates),
        ).all()
    }
    return sorted({d.year for d in candidates if d not in holidays})
