"""Service for the configurable special days 24.12. and 31.12. (#146).

Each of the two dates can independently be configured per practice
(tenant-scoped, stored in ``system_settings``) as one of:

- ``working_day`` (default, fully backward compatible — today both days are
  treated like any normal working day, no special handling at all),
- ``half_day``   (the daily target on that date is halved), or
- ``free``       (the daily target on that date is 0, like a public holiday).

When a day is ``free`` it additionally carries a ``counts_as_vacation`` flag:

- ``counts_as_vacation = False`` → **bezahlte Freistellung** (paid leave): the
  target drops to 0 and NOTHING is deducted from the vacation budget. This is
  fully handled by the target reduction alone.
- ``counts_as_vacation = True``  → **Urlaub** (vacation): the target drops to 0
  AND the day consumes one vacation day. The deduction is applied
  non-invasively in ``calculation_service.get_vacation_account`` — no Absence
  rows are generated (see ``vacation_deduction_days_for_year``).

Settings (per tenant, in ``system_settings``):

- ``special_day_dec24_mode``                 ∈ {working_day, half_day, free}
- ``special_day_dec24_counts_as_vacation``   bool (only meaningful when free)
- ``special_day_dec31_mode``                 ∈ {working_day, half_day, free}
- ``special_day_dec31_counts_as_vacation``   bool (only meaningful when free)

No new DB table or migration is required — the existing ``system_setting``
key/value store is reused, mirroring the ``holiday_state`` setting pattern.
"""

from datetime import date
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting

# Valid modes for a special day.
MODE_WORKING_DAY = "working_day"
MODE_HALF_DAY = "half_day"
MODE_FREE = "free"
VALID_MODES = {MODE_WORKING_DAY, MODE_HALF_DAY, MODE_FREE}

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
}

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


def get_special_day_settings(db: Session, tenant_id) -> Dict[str, object]:
    """Return the four special-day settings for a tenant (with defaults).

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
    }


def get_special_day_config(db: Session, tenant_id, year: int) -> Dict[date, Dict[str, object]]:
    """Resolve the special-day configuration to concrete dates for ``year``.

    Returns a mapping ``{date(year, 12, 24): {...}, date(year, 12, 31): {...}}``
    where each value is ``{"mode": str, "counts_as_vacation": bool}``. Days
    configured as ``working_day`` are still included (mode == working_day) so
    callers can distinguish "not configured" (date absent) from "explicitly a
    normal working day"; in practice both behave identically.

    The lookup issues a single SELECT for all of the tenant's special-day
    settings to avoid one query per key in the hot reporting loops.
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
        }
    return config


def special_day_target_factor(
    target_date: date,
    config: Dict[date, Dict[str, object]],
) -> Optional[Decimal]:
    """Return the target multiplier a special-day rule imposes on ``target_date``.

    - ``None``           → no special-day rule applies (treat the day normally).
    - ``Decimal('0.5')`` → ``half_day``: the daily target is halved.
    - ``Decimal('0')``   → ``free``: the daily target is 0 (like a holiday).

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
    # working_day → no change.
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
