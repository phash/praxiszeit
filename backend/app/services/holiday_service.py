from datetime import date, datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.config import settings
from app.services.timezone_service import today_local


# German translations for holiday names returned by workalendar
HOLIDAY_NAME_DE = {
    # Fixed holidays
    "New year": "Neujahr",
    "New Year's Day": "Neujahr",
    "Epiphany": "Heilige Drei Könige",
    "Labour Day": "Tag der Arbeit",
    "German Unity Day": "Tag der Deutschen Einheit",
    "All Saints Day": "Allerheiligen",
    "Christmas Day": "1. Weihnachtstag",
    "Second Day of Christmas": "2. Weihnachtstag",
    "Christmas": "1. Weihnachtstag",
    "Second Christmas Day": "2. Weihnachtstag",
    # Easter-based
    "Good Friday": "Karfreitag",
    "Easter Sunday": "Ostersonntag",
    "Easter Monday": "Ostermontag",
    "Ascension Thursday": "Christi Himmelfahrt",
    "Ascension Day": "Christi Himmelfahrt",
    "Whit Sunday": "Pfingstsonntag",
    "Whit Monday": "Pfingstmontag",
    "Corpus Christi": "Fronleichnam",
    # Regional
    "Assumption of Mary to Heaven": "Mariä Himmelfahrt",
    "Assumption of Mary": "Mariä Himmelfahrt",
    "Day of Repentance and Prayer": "Buß- und Bettag",
    "Reformation Day": "Reformationstag",
    "Peace Festival": "Augsburger Hohes Friedensfest",
    "St. Stephen's Day": "2. Weihnachtstag",
    "International Women's Day": "Internationaler Frauentag",
    "World Children's Day": "Weltkindertag",
}

# Supported German states mapping (class names from workalendar.europe)
SUPPORTED_STATES = {
    "Baden-Württemberg": "workalendar.europe.BadenWurttemberg",
    "Bayern": "workalendar.europe.Bavaria",
    "Berlin": "workalendar.europe.Berlin",
    "Brandenburg": "workalendar.europe.Brandenburg",
    "Bremen": "workalendar.europe.Bremen",
    "Hamburg": "workalendar.europe.Hamburg",
    "Hessen": "workalendar.europe.Hesse",
    "Mecklenburg-Vorpommern": "workalendar.europe.MecklenburgVorpommern",
    "Niedersachsen": "workalendar.europe.LowerSaxony",
    "Nordrhein-Westfalen": "workalendar.europe.NorthRhineWestphalia",
    "Rheinland-Pfalz": "workalendar.europe.RhinelandPalatinate",
    "Saarland": "workalendar.europe.Saarland",
    "Sachsen": "workalendar.europe.Saxony",
    "Sachsen-Anhalt": "workalendar.europe.SaxonyAnhalt",
    "Schleswig-Holstein": "workalendar.europe.SchleswigHolstein",
    "Thüringen": "workalendar.europe.Thuringia",
}


def _translate_name(name: str) -> str:
    """Translate English holiday name to German."""
    return HOLIDAY_NAME_DE.get(name, name)


def get_holiday_state(db: Session, tenant_id=None) -> str:
    """Read the holiday state from SystemSetting, fall back to config."""
    query = db.query(SystemSetting).filter(SystemSetting.key == "holiday_state")
    if tenant_id is not None:
        query = query.filter(SystemSetting.tenant_id == tenant_id)
    s = query.first()
    if s and s.value in SUPPORTED_STATES:
        return s.value
    return settings.HOLIDAY_STATE


def _get_calendar(state: Optional[str] = None):
    """Return the workalendar calendar for the given or configured state."""
    state = state or settings.HOLIDAY_STATE
    module_path = SUPPORTED_STATES.get(state, "workalendar.europe.Bavaria")
    module_name, class_name = module_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_name)
    cal_class = getattr(module, class_name)
    return cal_class()


def sync_holidays(db: Session, year: int, state: Optional[str] = None, tenant_id=None) -> int:
    """
    Synchronize public holidays for a given year into the database.
    Caller is responsible for committing.
    Returns number of holidays added.
    """
    cal = _get_calendar(state)
    holidays = cal.holidays(year)

    count = 0
    for holiday_date, holiday_name in holidays:
        german_name = _translate_name(holiday_name)

        query = db.query(PublicHoliday).filter(PublicHoliday.date == holiday_date)
        if tenant_id is not None:
            query = query.filter(PublicHoliday.tenant_id == tenant_id)
        existing = query.first()

        if not existing:
            holiday = PublicHoliday(
                date=holiday_date,
                name=german_name,
                year=year,
                tenant_id=tenant_id,
                is_custom=False,
                source="workalendar",
            )
            db.add(holiday)
            count += 1
        elif existing.source == "admin":
            # #143: an admin custom holiday already covers this date — never
            # overwrite its name with the workalendar name. The date is already
            # a holiday for Sollzeit purposes, so no workalendar row is needed.
            continue
        elif existing.name != german_name:
            existing.name = german_name

    # F-034: writes invalidate the cache for this (tenant, year)
    invalidate_holiday_cache(tenant_id=tenant_id, year=year)

    # No commit – let the caller manage the transaction
    return count


def get_holidays(db: Session, year: int, tenant_id=None) -> List[PublicHoliday]:
    """Get all public holidays for a given year, scoped to the tenant.

    F-026: explicit tenant filter — RLS already scopes, but holiday rows
    are global-looking and easy to leak if the GUC is unset for any reason.
    """
    query = db.query(PublicHoliday).filter(PublicHoliday.year == year)
    if tenant_id is not None:
        query = query.filter(PublicHoliday.tenant_id == tenant_id)
    return query.order_by(PublicHoliday.date).all()


def is_holiday(db: Session, check_date: date, tenant_id=None) -> bool:
    """
    Check if a given date is a public holiday.

    F-034: caching. Holidays change only once a year at sync-time, but
    hot loops (reports, list_time_entries enrichment, dashboard team view)
    may call this per entry. We cache the set of holiday dates per
    (tenant_id, year) in process memory; the cache is explicitly
    invalidated in sync_holidays / sync_current_and_next_year /
    delete_all_holidays below.
    """
    holiday_dates = _get_holiday_dates(db, check_date.year, tenant_id=tenant_id)
    return check_date in holiday_dates


# ── F-034: per-(tenant, year) holiday cache ──────────────────────────────
# Key:   (tenant_id, year)      value: frozenset[date]
# Scope: process-local; invalidated on any holiday write.
_HOLIDAY_CACHE: dict = {}


def _get_holiday_dates(db: Session, year: int, tenant_id=None) -> frozenset:
    """Return the cached set of holiday dates for the given (tenant, year).

    On first access, loads via a single SELECT. Thread-safety: a torn cache
    read between two workers is harmless — at worst two workers run the
    same SELECT once; subsequent reads are both O(1).
    """
    key = (tenant_id, year)
    cached = _HOLIDAY_CACHE.get(key)
    if cached is not None:
        return cached

    query = db.query(PublicHoliday.date).filter(PublicHoliday.year == year)
    if tenant_id is not None:
        query = query.filter(PublicHoliday.tenant_id == tenant_id)
    dates = frozenset(row[0] for row in query.all())
    _HOLIDAY_CACHE[key] = dates
    return dates


def invalidate_holiday_cache(tenant_id=None, year: Optional[int] = None) -> None:
    """Drop cached holiday sets. Called after any holiday-table write."""
    if tenant_id is None and year is None:
        _HOLIDAY_CACHE.clear()
        return
    for key in list(_HOLIDAY_CACHE.keys()):
        k_tenant, k_year = key
        if (tenant_id is None or k_tenant == tenant_id) and (
            year is None or k_year == year
        ):
            _HOLIDAY_CACHE.pop(key, None)


def delete_all_holidays(db: Session, tenant_id=None, source: Optional[str] = None) -> int:
    """Delete holidays from the database. If tenant_id given, only for that tenant.

    ``source`` (#143): when given (e.g. ``'workalendar'``), only rows with that
    provenance are deleted. The Bundesland-change resync passes
    ``source='workalendar'`` so admin-created custom holidays
    (``source='admin'``) survive the resync (REQ-3). Omitting ``source`` keeps
    the original "purge everything" behaviour.

    Caller is responsible for committing."""
    query = db.query(PublicHoliday)
    if tenant_id is not None:
        query = query.filter(PublicHoliday.tenant_id == tenant_id)
    if source is not None:
        query = query.filter(PublicHoliday.source == source)
    count = query.count()
    query.delete()
    # F-034: invalidate the cache after bulk-delete
    invalidate_holiday_cache(tenant_id=tenant_id)
    # No commit – let the caller manage the transaction
    return count


def sync_current_and_next_year(db: Session, state: Optional[str] = None, tenant_id=None) -> dict:
    """
    Sync holidays for current and next year.
    Called during application startup and when Bundesland changes.
    Performs a single commit at the end.
    """
    if state is None:
        state = get_holiday_state(db, tenant_id=tenant_id)

    current_year = today_local().year
    next_year = current_year + 1

    # Force-update names of all existing workalendar holidays to German
    # (no intermediate commit). #143: skip admin custom holidays — their names
    # are user-chosen and must not be run through the translation table.
    query = db.query(PublicHoliday).filter(PublicHoliday.source == "workalendar")
    if tenant_id is not None:
        query = query.filter(PublicHoliday.tenant_id == tenant_id)
    all_holidays = query.all()
    for h in all_holidays:
        german_name = _translate_name(h.name)
        if german_name != h.name:
            h.name = german_name

    current_count = sync_holidays(db, current_year, state, tenant_id=tenant_id)
    next_count = sync_holidays(db, next_year, state, tenant_id=tenant_id)

    db.commit()  # Single commit for the entire operation

    return {
        "current_year": current_year,
        "current_count": current_count,
        "next_year": next_year,
        "next_count": next_count,
        "state": state,
    }


def get_supported_states() -> List[str]:
    """Return list of supported German federal states."""
    return sorted(SUPPORTED_STATES.keys())
