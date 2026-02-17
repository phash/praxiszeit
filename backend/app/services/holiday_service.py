from datetime import date, datetime
from typing import List
from sqlalchemy.orm import Session
from app.models.public_holiday import PublicHoliday
from app.config import settings


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

# Supported German states mapping
SUPPORTED_STATES = {
    "Bayern": "workalendar.europe.Bavaria",
    "Baden-Württemberg": "workalendar.europe.BadenWurttemberg",
    "Berlin": "workalendar.europe.Berlin",
    "Brandenburg": "workalendar.europe.Brandenburg",
    "Bremen": "workalendar.europe.Bremen",
    "Hamburg": "workalendar.europe.Hamburg",
    "Hessen": "workalendar.europe.Hessen",
    "Mecklenburg-Vorpommern": "workalendar.europe.MecklenburgVorpommern",
    "Niedersachsen": "workalendar.europe.NordrheinWestfalen",  # closest
    "Nordrhein-Westfalen": "workalendar.europe.NordrheinWestfalen",
    "Rheinland-Pfalz": "workalendar.europe.RheinlandPfalz",
    "Saarland": "workalendar.europe.Saarland",
    "Sachsen": "workalendar.europe.Sachsen",
    "Sachsen-Anhalt": "workalendar.europe.SachsenAnhalt",
    "Schleswig-Holstein": "workalendar.europe.SchleswigHolstein",
    "Thüringen": "workalendar.europe.Thueringen",
}


def _translate_name(name: str) -> str:
    """Translate English holiday name to German."""
    return HOLIDAY_NAME_DE.get(name, name)


def _get_calendar():
    """Return the workalendar calendar for the configured state."""
    state = settings.HOLIDAY_STATE
    module_path = SUPPORTED_STATES.get(state, "workalendar.europe.Bavaria")
    module_name, class_name = module_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_name)
    cal_class = getattr(module, class_name)
    return cal_class()


def sync_holidays(db: Session, year: int) -> int:
    """
    Synchronize public holidays for a given year into the database.
    Uses the configured state (HOLIDAY_STATE env var).
    Translates holiday names to German.

    Returns number of holidays synced.
    """
    cal = _get_calendar()
    holidays = cal.holidays(year)

    count = 0
    for holiday_date, holiday_name in holidays:
        german_name = _translate_name(holiday_name)

        existing = db.query(PublicHoliday).filter(
            PublicHoliday.date == holiday_date
        ).first()

        if not existing:
            holiday = PublicHoliday(
                date=holiday_date,
                name=german_name,
                year=year
            )
            db.add(holiday)
            count += 1
        elif existing.name != german_name:
            # Update name if translation changed
            existing.name = german_name

    db.commit()
    return count


def get_holidays(db: Session, year: int) -> List[PublicHoliday]:
    """Get all public holidays for a given year."""
    return db.query(PublicHoliday).filter(
        PublicHoliday.year == year
    ).order_by(PublicHoliday.date).all()


def is_holiday(db: Session, check_date: date) -> bool:
    """Check if a given date is a public holiday."""
    holiday = db.query(PublicHoliday).filter(
        PublicHoliday.date == check_date
    ).first()
    return holiday is not None


def sync_current_and_next_year(db: Session) -> dict:
    """
    Sync holidays for current and next year.
    Called during application startup.
    Also updates names of existing holidays to German.
    """
    current_year = datetime.now().year
    next_year = current_year + 1

    # Force-update names of all existing holidays to German
    all_holidays = db.query(PublicHoliday).all()
    for h in all_holidays:
        german_name = _translate_name(h.name)
        if german_name != h.name:
            h.name = german_name
    db.commit()

    current_count = sync_holidays(db, current_year)
    next_count = sync_holidays(db, next_year)

    return {
        "current_year": current_year,
        "current_count": current_count,
        "next_year": next_year,
        "next_count": next_count,
        "state": settings.HOLIDAY_STATE,
    }


def get_supported_states() -> List[str]:
    """Return list of supported German federal states."""
    return sorted(SUPPORTED_STATES.keys())
