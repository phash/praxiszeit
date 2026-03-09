"""Tests für holiday_service."""
import pytest
from datetime import date
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.services import holiday_service


@pytest.fixture
def public_holiday(db):
    """Ein Feiertag (Neujahr 2026) für Tests."""
    h = PublicHoliday(
        date=date(2026, 1, 1),
        name="Neujahr",
        year=2026,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


# --- is_holiday ---

def test_is_holiday_true_for_existing(db, public_holiday):
    """`is_holiday` → True für eingetragenen Feiertag."""
    assert holiday_service.is_holiday(db, date(2026, 1, 1)) is True


def test_is_holiday_false_for_non_holiday(db, public_holiday):
    """`is_holiday` → False für normalen Tag."""
    assert holiday_service.is_holiday(db, date(2026, 1, 2)) is False


# --- get_holiday_state ---

def test_get_holiday_state_from_db(db):
    """`get_holiday_state` liest aus DB-SystemSetting."""
    setting = SystemSetting(key="holiday_state", value="Bayern")
    db.add(setting)
    db.commit()
    result = holiday_service.get_holiday_state(db)
    assert result == "Bayern"


def test_get_holiday_state_fallback(db):
    """`get_holiday_state` → Fallback auf settings.HOLIDAY_STATE wenn kein DB-Eintrag."""
    from app.config import settings
    result = holiday_service.get_holiday_state(db)
    assert result == settings.HOLIDAY_STATE


# --- delete_all_holidays ---

def test_delete_all_holidays_removes_entries(db, public_holiday):
    """`delete_all_holidays` → löscht alle Einträge, gibt Anzahl zurück."""
    count = holiday_service.delete_all_holidays(db)
    db.flush()
    assert count == 1
    remaining = db.query(PublicHoliday).count()
    assert remaining == 0


def test_delete_all_holidays_no_commit(db, public_holiday):
    """`delete_all_holidays` → kein db.commit(), Rollback stellt Daten wieder her."""
    holiday_service.delete_all_holidays(db)
    db.rollback()
    remaining = db.query(PublicHoliday).count()
    assert remaining == 1


# --- sync_holidays ---

def test_sync_holidays_adds_holidays(db):
    """`sync_holidays` → fügt Feiertage ein, gibt Anzahl zurück."""
    count = holiday_service.sync_holidays(db, 2026, state="Bayern")
    assert count > 0
    db.commit()
    total = db.query(PublicHoliday).filter(PublicHoliday.year == 2026).count()
    assert total == count


def test_sync_holidays_updates_existing_name(db):
    """`sync_holidays` → updated Namen existierender Einträge wenn abweichend."""
    h = PublicHoliday(date=date(2026, 1, 1), name="WRONG_NAME", year=2026)
    db.add(h)
    db.commit()
    holiday_service.sync_holidays(db, 2026, state="Bayern")
    db.commit()
    refreshed = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 1, 1)).first()
    assert refreshed.name == "Neujahr"


def test_sync_holidays_no_commit(db):
    """`sync_holidays` → kein db.commit(), Rollback verwirft Feiertage."""
    holiday_service.sync_holidays(db, 2026, state="Bayern")
    db.rollback()
    total = db.query(PublicHoliday).count()
    assert total == 0


# --- sync_current_and_next_year ---

def test_sync_current_and_next_year_returns_dict(db):
    """`sync_current_and_next_year` → committet, gibt dict mit korrekten Keys zurück."""
    result = holiday_service.sync_current_and_next_year(db, state="Bayern")
    assert "current_year" in result
    assert "next_year" in result
    assert "current_count" in result
    assert "next_count" in result
    assert result["state"] == "Bayern"
    total = db.query(PublicHoliday).count()
    assert total > 0
