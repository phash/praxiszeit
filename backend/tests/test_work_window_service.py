"""#201 → Spec 2026-10-08: Kappung gegen Altfenster (Einblock-Tage aus 073).

Kappungsparität: dieselben Fälle wie bis 1.19.3, jetzt über ``work_blocks``
(``legacy_week``) statt ``scheduled_*`` und mit ``ClampResult``."""
from datetime import date, time

import pytest

from app.models import TimeEntry, User, UserRole
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.services import work_window_service as wws
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import legacy_week

MON = date(2026, 6, 1)
EASTER_MONDAY = date(2026, 4, 6)
DEC24 = date(2026, 12, 24)


def _user(**kw):
    defaults = dict(
        username="w", email="w@x.de", password_hash="h", first_name="W", last_name="W",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
        track_hours=True,
    )
    defaults.update(kw)
    return User(**defaults)


def _c(db, user, d, start, end, grace=15):
    return wws.clamp(db, user, d, start, end, grace, credit_override=False)


def test_no_window_no_clamp(db):
    assert _c(db, _user(), MON, time(7, 0), time(17, 0)) == wws.ClampResult(
        time(7, 0), time(17, 0), None, None, 0, None)


def test_early_start_capped(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", None))), MON, time(7, 0), time(16, 0))
    assert (r.eff_start, r.raw_start, r.eff_end, r.raw_end) == (time(7, 45), time(7, 0), time(16, 0), None)
    assert (r.uncredited_minutes, r.grace_minutes) == (0, 15)


def test_within_grace_not_capped(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", None))), MON, time(7, 50), time(16, 0))
    assert r.eff_start == time(7, 50) and r.raw_start is None


def test_late_end_capped(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=(None, "17:00"))), MON, time(8, 0), time(18, 30))
    assert r.eff_end == time(17, 15) and r.raw_end == time(18, 30)


def test_track_hours_false_skips(db):
    r = _c(db, _user(track_hours=False, work_blocks=legacy_week(mon=("08:00", None))), MON, time(6, 0), time(16, 0))
    assert r.eff_start == time(6, 0) and r.raw_start is None and r.grace_minutes is None


def test_open_end_none_passthrough(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", "17:00"))), MON, time(6, 0), None)
    assert r.eff_end is None and r.raw_end is None


def test_grace_shift_clamps_to_day_bounds(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=(None, "23:50"))), MON, time(8, 0), time(23, 59))
    assert r.eff_end == time(23, 59)


def test_entry_entirely_before_window_zero_credit(db):
    # Nachmittagsschicht-Fenster, Vormittags-Eintrag → komplett außerhalb.
    # #201-Spec §5: 0 angerechnete Stunden (eff_start == eff_end → net 0),
    # aber beide Rohstempel bleiben für den §16-Nachweis erhalten.
    r = _c(db, _user(work_blocks=legacy_week(mon=("14:00", "18:00"))), MON, time(8, 0), time(9, 0))
    assert r.eff_start == r.eff_end
    assert (r.raw_start, r.raw_end) == (time(8, 0), time(9, 0))


def test_entry_entirely_after_window_zero_credit(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", "10:00"))), MON, time(14, 0), time(15, 0))
    assert r.eff_start == r.eff_end
    assert (r.raw_start, r.raw_end) == (time(14, 0), time(15, 0))


def test_entirely_outside_entry_has_zero_net_hours(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", "10:00"))), MON, time(14, 0), time(15, 0))
    te = TimeEntry(start_time=r.eff_start, end_time=r.eff_end, break_minutes=0,
                   raw_start_time=r.raw_start, raw_end_time=r.raw_end)
    assert te.net_hours == 0
    assert te.raw_start_time == time(14, 0) and te.raw_end_time == time(15, 0)


def test_half_open_placeholders_behave_like_072(db):
    """Spec 5.3: Platzhalter 00:00/23:59 verhalten sich wie das fehlende Ende."""
    start_only = _user(work_blocks=legacy_week(mon=("08:00", None)))
    r = _c(db, start_only, MON, time(9, 0), time(23, 59))
    assert (r.eff_end, r.raw_end) == (time(23, 59), None)
    # Review Task 3: auch ein Ende mit Sekunden (API-Client) bleibt ungekappt —
    # unter 072 gab es ohne Soll-Ende gar keine Ende-Kappung und keine Warnung.
    r = _c(db, start_only, MON, time(9, 0), time(23, 59, 30))
    assert (r.eff_end, r.raw_end) == (time(23, 59, 30), None)
    assert wws.clamp_warning_text(db, start_only, MON, r, for_employee=False) is None
    # Kontrolle: ein echtes spätes Ende (23:50 + 15 → Hülle 23:59) kappt die
    # Sekunden weiter wie 072.
    late_end = _user(work_blocks=legacy_week(mon=("08:00", "23:50")))
    r = _c(db, late_end, MON, time(9, 0), time(23, 59, 30))
    assert (r.eff_end, r.raw_end) == (time(23, 59), time(23, 59, 30))
    end_only = _user(work_blocks=legacy_week(mon=(None, "17:00")))
    r = _c(db, end_only, MON, time(0, 0), time(16, 0))
    assert (r.eff_start, r.raw_start) == (time(0, 0), None)


# ── #484: keine Kappung an soll-freien Werktagen ──────────────────────────────
# Die Blöcke beschreiben die Lage der Sollzeit. Am Wochenende gibt es keine; ein
# Feiertag auf einem Werktag bekam bis 1.19.2 trotzdem das Fenster seines
# Wochentags — ein KV-Dienst am Ostermontag wurde gekappt, derselbe Dienst am
# Sonntag nicht. Feiertage und als "frei" konfigurierte Sondertage haben wie das
# Wochenende kein Soll und deshalb keine Blöcke.

def _windowed_user():
    return _user(
        tenant_id=DEFAULT_TENANT_ID,
        work_blocks=legacy_week(mon=("08:00", "17:00"), thu=("08:00", "17:00")),
    )


def _holiday(db, d, tenant_id=DEFAULT_TENANT_ID):
    db.add(PublicHoliday(date=d, name="Feiertag", year=d.year, tenant_id=tenant_id))
    db.commit()
    invalidate_holiday_cache()


def _dec24_mode(db, mode):
    db.add(SystemSetting(key="special_day_dec24_mode", value=mode, tenant_id=DEFAULT_TENANT_ID))
    db.commit()


@pytest.fixture
def fresh_holiday_cache():
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


def test_window_still_applies_on_ordinary_monday(db, default_tenant, fresh_holiday_cache):
    r = _c(db, _windowed_user(), MON, time(7, 0), time(18, 0))
    assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == (time(7, 45), time(17, 15), time(7, 0), time(18, 0))


def test_holiday_on_weekday_has_no_window(db, default_tenant, fresh_holiday_cache):
    _holiday(db, EASTER_MONDAY)
    r = _c(db, _windowed_user(), EASTER_MONDAY, time(7, 0), time(18, 0))
    assert r == wws.ClampResult(time(7, 0), time(18, 0), None, None, 0, None)
    assert wws.get_scheduled_blocks(db, _windowed_user(), EASTER_MONDAY) == []


def test_holiday_of_another_tenant_does_not_lift_the_window(db, default_tenant, fresh_holiday_cache):
    import uuid
    other = Tenant(id=uuid.uuid4(), name="Andere Praxis", slug="andere-praxis")
    db.add(other)
    db.commit()
    _holiday(db, EASTER_MONDAY, tenant_id=other.id)
    r = _c(db, _windowed_user(), EASTER_MONDAY, time(7, 0), time(18, 0))
    assert (r.raw_start, r.raw_end) == (time(7, 0), time(18, 0))


def test_free_special_day_has_no_window(db, default_tenant, fresh_holiday_cache):
    _dec24_mode(db, "free")
    r = _c(db, _windowed_user(), DEC24, time(7, 0), time(18, 0))
    assert r == wws.ClampResult(time(7, 0), time(18, 0), None, None, 0, None)


def test_half_special_day_keeps_the_window(db, default_tenant, fresh_holiday_cache):
    _dec24_mode(db, "half_day")
    r = _c(db, _windowed_user(), DEC24, time(7, 0), time(18, 0))
    assert (r.raw_start, r.raw_end) == (time(7, 0), time(18, 0))
