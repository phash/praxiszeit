from datetime import date, datetime
from typing import List
from sqlalchemy.orm import Session
from workalendar.europe import Bavaria
from app.models.public_holiday import PublicHoliday


def sync_holidays(db: Session, year: int) -> int:
    """
    Synchronize Bavarian public holidays for a given year into the database.
    Uses upsert logic to avoid duplicates.

    Args:
        db: Database session
        year: Year to sync holidays for

    Returns:
        Number of holidays synced
    """
    cal = Bavaria()
    holidays = cal.holidays(year)

    count = 0
    for holiday_date, holiday_name in holidays:
        # Check if holiday already exists
        existing = db.query(PublicHoliday).filter(
            PublicHoliday.date == holiday_date
        ).first()

        if not existing:
            holiday = PublicHoliday(
                date=holiday_date,
                name=holiday_name,
                year=year
            )
            db.add(holiday)
            count += 1

    db.commit()
    return count


def get_holidays(db: Session, year: int) -> List[PublicHoliday]:
    """
    Get all public holidays for a given year.

    Args:
        db: Database session
        year: Year to get holidays for

    Returns:
        List of PublicHoliday objects
    """
    return db.query(PublicHoliday).filter(
        PublicHoliday.year == year
    ).order_by(PublicHoliday.date).all()


def is_holiday(db: Session, check_date: date) -> bool:
    """
    Check if a given date is a public holiday.

    Args:
        db: Database session
        check_date: Date to check

    Returns:
        True if the date is a public holiday, False otherwise
    """
    holiday = db.query(PublicHoliday).filter(
        PublicHoliday.date == check_date
    ).first()
    return holiday is not None


def sync_current_and_next_year(db: Session) -> dict:
    """
    Sync holidays for current and next year.
    Called during application startup.

    Args:
        db: Database session

    Returns:
        Dict with sync results
    """
    current_year = datetime.now().year
    next_year = current_year + 1

    current_count = sync_holidays(db, current_year)
    next_count = sync_holidays(db, next_year)

    return {
        "current_year": current_year,
        "current_count": current_count,
        "next_year": next_year,
        "next_count": next_count
    }
