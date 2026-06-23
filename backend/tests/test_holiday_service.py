"""Tests für holiday_service."""
import pytest
from datetime import date
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.services import holiday_service
from app.config import settings
from tests.conftest import DEFAULT_TENANT_ID


@pytest.fixture
def public_holiday(db, default_tenant):
    """Ein Feiertag (Neujahr 2026) für Tests."""
    h = PublicHoliday(
        date=date(2026, 1, 1),
        name="Neujahr",
        year=2026,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


# --- is_holiday ---

def test_is_holiday_true_for_existing(db, public_holiday):
    """Prüft dass eingetragene Feiertage erkannt werden — wichtig für korrekte Soll-Stunden-Berechnung."""
    assert holiday_service.is_holiday(db, date(2026, 1, 1)) is True


def test_is_holiday_false_for_non_holiday(db, public_holiday):
    """Prüft dass normale Arbeitstage nicht fälschlich als Feiertag erkannt werden."""
    assert holiday_service.is_holiday(db, date(2026, 1, 2)) is False


# --- get_holiday_state ---

def test_get_holiday_state_from_db(db):
    """Prüft dass das Bundesland aus der DB-SystemSetting gelesen wird — bestimmt länderspezifische Feiertage."""
    setting = SystemSetting(key="holiday_state", value="Bayern", tenant_id=DEFAULT_TENANT_ID)
    db.add(setting)
    db.commit()
    result = holiday_service.get_holiday_state(db)
    assert result == "Bayern"


def test_get_holiday_state_fallback(db):
    """Prüft dass ohne DB-Eintrag auf den Config-Fallback zurückgegriffen wird — verhindert Fehler bei Erstinstallation."""
    result = holiday_service.get_holiday_state(db)
    assert result == settings.HOLIDAY_STATE


# --- delete_all_holidays ---

def test_delete_all_holidays_removes_entries(db, public_holiday):
    """Prüft dass alle Feiertage gelöscht werden und die Anzahl korrekt zurückgegeben wird."""
    count = holiday_service.delete_all_holidays(db)
    assert count == 1
    remaining = db.query(PublicHoliday).count()
    assert remaining == 0


def test_delete_all_holidays_no_commit(db, public_holiday):
    """Prüft dass delete_all_holidays kein auto-commit macht — Caller kontrolliert die Transaktion."""
    holiday_service.delete_all_holidays(db)
    db.rollback()
    remaining = db.query(PublicHoliday).count()
    assert remaining == 1


# --- sync_holidays ---

def test_sync_holidays_adds_holidays(db, default_tenant):
    """Prüft dass sync_holidays Feiertage für das Bundesland einfügt — Basis für korrekte Soll-Berechnung."""
    count = holiday_service.sync_holidays(db, 2026, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
    assert count > 0
    db.commit()
    total = db.query(PublicHoliday).filter(PublicHoliday.year == 2026).count()
    assert total == count


def test_sync_holidays_updates_existing_name(db, default_tenant):
    """Prüft dass sync_holidays falsche Feiertagsnamen korrigiert statt Duplikate zu erzeugen."""
    h = PublicHoliday(date=date(2026, 1, 1), name="WRONG_NAME", year=2026, tenant_id=DEFAULT_TENANT_ID)
    db.add(h)
    db.commit()
    holiday_service.sync_holidays(db, 2026, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
    db.commit()
    refreshed = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 1, 1)).first()
    assert refreshed.name == "Neujahr"


def test_sync_holidays_no_commit(db, default_tenant):
    """Prüft dass sync_holidays kein auto-commit macht — ermöglicht atomares Sync+Delete in einer Transaktion."""
    holiday_service.sync_holidays(db, 2026, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
    db.rollback()
    total = db.query(PublicHoliday).count()
    assert total == 0


# --- sync_current_and_next_year ---

def test_sync_current_and_next_year_returns_dict(db, default_tenant):
    """Prüft dass sync_current_and_next_year beide Jahre synchronisiert und ein vollständiges Ergebnis-Dict liefert."""
    result = holiday_service.sync_current_and_next_year(db, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
    assert "current_year" in result
    assert "next_year" in result
    assert "current_count" in result
    assert "next_count" in result
    assert result["state"] == "Bayern"
    assert result["current_count"] > 0
    assert result["next_count"] > 0
    total = db.query(PublicHoliday).count()
    assert total > 0


# --- python-holidays-Migration (#175): korrekte + aktuelle Bundesland-Feiertage ---

def test_bavaria_keeps_assumption_day(db, default_tenant):
    """Bayern behält Mariä Himmelfahrt (15.8., kath. Kategorie) wie zuvor unter workalendar."""
    holiday_service.sync_holidays(db, 2026, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
    db.commit()
    h = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 8, 15)).first()
    assert h is not None and h.name == "Mariä Himmelfahrt"


def test_mv_has_womens_day(db, default_tenant):
    """MV: Internationaler Frauentag (8.3., gesetzlich seit 2023) — das unmaintained workalendar kannte ihn nicht."""
    holiday_service.sync_holidays(db, 2026, state="Mecklenburg-Vorpommern", tenant_id=DEFAULT_TENANT_ID)
    db.commit()
    assert db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 3, 8)).first() is not None


def test_holiday_names_normalized_to_project_spelling(db, default_tenant):
    """python-holidays-Namen auf Projekt-Schreibweise normalisiert (z. B. 'Erster Mai' -> 'Tag der Arbeit')."""
    holiday_service.sync_holidays(db, 2026, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
    db.commit()
    mayday = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 5, 1)).first()
    assert mayday is not None and mayday.name == "Tag der Arbeit"
    xmas = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 12, 25)).first()
    assert xmas is not None and xmas.name == "1. Weihnachtstag"


def test_sync_holidays_idempotent(db, default_tenant):
    """Zweiter Sync desselben Jahres fügt nichts hinzu — keine Duplikate."""
    holiday_service.sync_holidays(db, 2026, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
    db.commit()
    second = holiday_service.sync_holidays(db, 2026, state="Bayern", tenant_id=DEFAULT_TENANT_ID)
    db.commit()
    assert second == 0


def test_german_holidays_rejects_unknown_state():
    """Unbekanntes Bundesland -> ValueError statt stillem Fallback auf Bayern."""
    with pytest.raises(ValueError):
        holiday_service._german_holidays("Tirol", 2026)
