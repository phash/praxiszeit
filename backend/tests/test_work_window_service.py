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


def test_no_window_no_clamp():
    u = _user()
    eff_s, eff_e, raw_s, raw_e = wws.clamp(u, MON, time(7, 0), time(17, 0), 15)
    assert (eff_s, eff_e, raw_s, raw_e) == (time(7, 0), time(17, 0), None, None)


def test_early_start_capped():
    u = _user(scheduled_start_monday=time(8, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(u, MON, time(7, 0), time(16, 0), 15)
    assert eff_s == time(7, 45)
    assert raw_s == time(7, 0)
    assert eff_e == time(16, 0) and raw_e is None


def test_within_grace_not_capped():
    u = _user(scheduled_start_monday=time(8, 0))
    eff_s, _, raw_s, _ = wws.clamp(u, MON, time(7, 50), time(16, 0), 15)
    assert eff_s == time(7, 50) and raw_s is None


def test_late_end_capped():
    u = _user(scheduled_end_monday=time(17, 0))
    _, eff_e, _, raw_e = wws.clamp(u, MON, time(8, 0), time(18, 30), 15)
    assert eff_e == time(17, 15) and raw_e == time(18, 30)


def test_track_hours_false_skips():
    u = _user(track_hours=False, scheduled_start_monday=time(8, 0))
    eff_s, _, raw_s, _ = wws.clamp(u, MON, time(6, 0), time(16, 0), 15)
    assert eff_s == time(6, 0) and raw_s is None


def test_open_end_none_passthrough():
    u = _user(scheduled_start_monday=time(8, 0), scheduled_end_monday=time(17, 0))
    eff_s, eff_e, _, raw_e = wws.clamp(u, MON, time(6, 0), None, 15)
    assert eff_e is None and raw_e is None


def test_grace_shift_clamps_to_day_bounds():
    u = _user(scheduled_end_monday=time(23, 50))
    _, eff_e, _, _ = wws.clamp(u, MON, time(8, 0), time(23, 59), 15)
    assert eff_e == time(23, 59)


def test_entry_entirely_before_window_zero_credit():
    # Nachmittagsschicht-Fenster, Vormittags-Eintrag → komplett außerhalb.
    # #201-Spec §5: 0 angerechnete Stunden (eff_start == eff_end → net 0),
    # aber beide Rohstempel bleiben für den §16-Nachweis erhalten.
    u = _user(scheduled_start_monday=time(14, 0), scheduled_end_monday=time(18, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(u, MON, time(8, 0), time(9, 0), 15)
    assert eff_s == eff_e          # angerechnete Zeit kollabiert auf einen Punkt → net 0
    assert raw_s == time(8, 0)     # Originalstart bewahrt
    assert raw_e == time(9, 0)     # Originalende bewahrt


def test_entry_entirely_after_window_zero_credit():
    u = _user(scheduled_start_monday=time(8, 0), scheduled_end_monday=time(10, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(u, MON, time(14, 0), time(15, 0), 15)
    assert eff_s == eff_e
    assert raw_s == time(14, 0)
    assert raw_e == time(15, 0)


def test_entirely_outside_entry_has_zero_net_hours():
    # Die kollabierte Effektivzeit erzeugt auf dem TimeEntry net_hours = 0.
    u = _user(scheduled_start_monday=time(8, 0), scheduled_end_monday=time(10, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(u, MON, time(14, 0), time(15, 0), 15)
    te = TimeEntry(
        start_time=eff_s, end_time=eff_e, break_minutes=0,
        raw_start_time=raw_s, raw_end_time=raw_e,
    )
    assert te.net_hours == 0
    # §16: die tatsächlichen Stempel bleiben rekonstruierbar.
    assert te.raw_start_time == time(14, 0) and te.raw_end_time == time(15, 0)
