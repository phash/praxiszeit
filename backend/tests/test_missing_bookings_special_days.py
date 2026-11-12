"""calc-02: 'Buchung fehlt' kennt freie/verkuerzte Sondertage."""
from datetime import date

from app.routers import dashboard
from tests.conftest import DEFAULT_TENANT_ID
from tests.setting_helpers import set_setting


def _missing(db, user, monkeypatch):
    # 30.12.2025: Dezember 1.-29. wird geprueft, 24.12. (Mittwoch) liegt darin.
    monkeypatch.setattr(dashboard, "today_local", lambda: date(2025, 12, 30))
    entries = dashboard._get_missing_bookings_for_user(db, user, tenant_id=DEFAULT_TENANT_ID)
    return {e.date for e in entries if e.type == "missing"}


def test_unconfigured_24_12_is_missing(db, test_user, monkeypatch):
    assert date(2025, 12, 24) in _missing(db, test_user, monkeypatch)


def test_free_special_day_is_not_missing(db, test_user, monkeypatch):
    set_setting(db, "special_day_dec24_mode", "free")
    set_setting(db, "special_day_dec24_counts_as_vacation", "false")
    missing = _missing(db, test_user, monkeypatch)
    assert date(2025, 12, 24) not in missing
    assert date(2025, 12, 23) in missing  # Nachbartag bleibt


def test_half_day_special_day_still_missing(db, test_user, monkeypatch):
    set_setting(db, "special_day_dec24_mode", "half_day")
    assert date(2025, 12, 24) in _missing(db, test_user, monkeypatch)
