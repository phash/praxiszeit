from datetime import date, time
from app.models import User, UserRole, TimeEntry
from app.services import work_window_service as wws


def _user(**kw):
    defaults = dict(
        username="w", email="w@x.de", password_hash="h", first_name="W", last_name="W",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
        track_hours=True,
    )
    defaults.update(kw)
    return User(**defaults)

MON = date(2026, 6, 1)  # Montag


def test_no_window_no_clamp(db):
    u = _user()
    eff_s, eff_e, raw_s, raw_e = wws.clamp(db, u, MON, time(7, 0), time(17, 0), 15)
    assert (eff_s, eff_e, raw_s, raw_e) == (time(7, 0), time(17, 0), None, None)


def test_early_start_capped(db):
    u = _user(scheduled_start_monday=time(8, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(db, u, MON, time(7, 0), time(16, 0), 15)
    assert eff_s == time(7, 45)
    assert raw_s == time(7, 0)
    assert eff_e == time(16, 0) and raw_e is None


def test_within_grace_not_capped(db):
    u = _user(scheduled_start_monday=time(8, 0))
    eff_s, _, raw_s, _ = wws.clamp(db, u, MON, time(7, 50), time(16, 0), 15)
    assert eff_s == time(7, 50) and raw_s is None


def test_late_end_capped(db):
    u = _user(scheduled_end_monday=time(17, 0))
    _, eff_e, _, raw_e = wws.clamp(db, u, MON, time(8, 0), time(18, 30), 15)
    assert eff_e == time(17, 15) and raw_e == time(18, 30)


def test_track_hours_false_skips(db):
    u = _user(track_hours=False, scheduled_start_monday=time(8, 0))
    eff_s, _, raw_s, _ = wws.clamp(db, u, MON, time(6, 0), time(16, 0), 15)
    assert eff_s == time(6, 0) and raw_s is None


def test_open_end_none_passthrough(db):
    u = _user(scheduled_start_monday=time(8, 0), scheduled_end_monday=time(17, 0))
    eff_s, eff_e, _, raw_e = wws.clamp(db, u, MON, time(6, 0), None, 15)
    assert eff_e is None and raw_e is None


def test_grace_shift_clamps_to_day_bounds(db):
    u = _user(scheduled_end_monday=time(23, 50))
    _, eff_e, _, _ = wws.clamp(db, u, MON, time(8, 0), time(23, 59), 15)
    assert eff_e == time(23, 59)


def test_entry_entirely_before_window_zero_credit(db):
    # Nachmittagsschicht-Fenster, Vormittags-Eintrag → komplett außerhalb.
    # #201-Spec §5: 0 angerechnete Stunden (eff_start == eff_end → net 0),
    # aber beide Rohstempel bleiben für den §16-Nachweis erhalten.
    u = _user(scheduled_start_monday=time(14, 0), scheduled_end_monday=time(18, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(db, u, MON, time(8, 0), time(9, 0), 15)
    assert eff_s == eff_e          # angerechnete Zeit kollabiert auf einen Punkt → net 0
    assert raw_s == time(8, 0)     # Originalstart bewahrt
    assert raw_e == time(9, 0)     # Originalende bewahrt


def test_entry_entirely_after_window_zero_credit(db):
    u = _user(scheduled_start_monday=time(8, 0), scheduled_end_monday=time(10, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(db, u, MON, time(14, 0), time(15, 0), 15)
    assert eff_s == eff_e
    assert raw_s == time(14, 0)
    assert raw_e == time(15, 0)


def test_entirely_outside_entry_has_zero_net_hours(db):
    # Die kollabierte Effektivzeit erzeugt auf dem TimeEntry net_hours = 0.
    u = _user(scheduled_start_monday=time(8, 0), scheduled_end_monday=time(10, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(db, u, MON, time(14, 0), time(15, 0), 15)
    te = TimeEntry(
        start_time=eff_s, end_time=eff_e, break_minutes=0,
        raw_start_time=raw_s, raw_end_time=raw_e,
    )
    assert te.net_hours == 0
    # §16: die tatsächlichen Stempel bleiben rekonstruierbar.
    assert te.raw_start_time == time(14, 0) and te.raw_end_time == time(15, 0)


# ── #484: kein Fenster an soll-freien Werktagen ─────────────────────────────
# Das Fenster beschreibt die Lage der Sollzeit. Am Wochenende gibt es keins; ein
# Feiertag auf einem Werktag bekam bis 1.19.2 trotzdem das Fenster seines
# Wochentags — ein KV-Dienst am Ostermontag wurde gekappt, derselbe Dienst am
# Sonntag nicht. Feiertage und als "frei" konfigurierte Sondertage haben wie das
# Wochenende kein Soll und deshalb kein Fenster.

import pytest
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID

EASTER_MONDAY = date(2026, 4, 6)   # Montag, gesetzlicher Feiertag
DEC24 = date(2026, 12, 24)          # Donnerstag


def _windowed_user():
    return _user(
        tenant_id=DEFAULT_TENANT_ID,
        scheduled_start_monday=time(8, 0), scheduled_end_monday=time(17, 0),
        scheduled_start_thursday=time(8, 0), scheduled_end_thursday=time(17, 0),
    )


def _holiday(db, d, tenant_id=DEFAULT_TENANT_ID):
    db.add(PublicHoliday(date=d, name="Feiertag", year=d.year, tenant_id=tenant_id))
    db.commit()
    invalidate_holiday_cache()


def _dec24_mode(db, mode):
    db.add(SystemSetting(key="special_day_dec24_mode", value=mode, tenant_id=DEFAULT_TENANT_ID))
    db.commit()


@pytest.fixture(autouse=False)
def fresh_holiday_cache():
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


def test_window_still_applies_on_ordinary_monday(db, default_tenant, fresh_holiday_cache):
    eff_s, eff_e, raw_s, raw_e = wws.clamp(db, _windowed_user(), MON, time(7, 0), time(18, 0), 15)
    assert (eff_s, eff_e, raw_s, raw_e) == (time(7, 45), time(17, 15), time(7, 0), time(18, 0))


def test_holiday_on_weekday_has_no_window(db, default_tenant, fresh_holiday_cache):
    _holiday(db, EASTER_MONDAY)
    eff_s, eff_e, raw_s, raw_e = wws.clamp(
        db, _windowed_user(), EASTER_MONDAY, time(7, 0), time(18, 0), 15,
    )
    assert (eff_s, eff_e, raw_s, raw_e) == (time(7, 0), time(18, 0), None, None)
    assert wws.get_scheduled_window(db, _windowed_user(), EASTER_MONDAY) == (None, None)


def test_holiday_of_another_tenant_does_not_lift_the_window(db, default_tenant, fresh_holiday_cache):
    from app.models.tenant import Tenant
    import uuid
    other = Tenant(id=uuid.uuid4(), name="Andere Praxis", slug="andere-praxis")
    db.add(other)
    db.commit()
    _holiday(db, EASTER_MONDAY, tenant_id=other.id)
    _, _, raw_s, raw_e = wws.clamp(db, _windowed_user(), EASTER_MONDAY, time(7, 0), time(18, 0), 15)
    assert (raw_s, raw_e) == (time(7, 0), time(18, 0))


def test_free_special_day_has_no_window(db, default_tenant, fresh_holiday_cache):
    _dec24_mode(db, "free")
    eff_s, eff_e, raw_s, raw_e = wws.clamp(db, _windowed_user(), DEC24, time(7, 0), time(18, 0), 15)
    assert (eff_s, eff_e, raw_s, raw_e) == (time(7, 0), time(18, 0), None, None)


def test_half_special_day_keeps_the_window(db, default_tenant, fresh_holiday_cache):
    # Ein halber Sondertag hat ein Soll (die Hälfte) — dort gilt das Fenster weiter.
    _dec24_mode(db, "half_day")
    _, _, raw_s, raw_e = wws.clamp(db, _windowed_user(), DEC24, time(7, 0), time(18, 0), 15)
    assert (raw_s, raw_e) == (time(7, 0), time(18, 0))
