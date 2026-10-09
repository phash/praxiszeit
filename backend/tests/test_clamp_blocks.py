"""Spec 6.1–6.3: Kappung gegen Arbeitszeit-Blöcke (Falltabelle K1–K21)."""
from datetime import time

import pytest

from app.models import TimeEntry, User, UserRole
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.services import work_window_service as wws
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_cases import EASTER_MONDAY, K_CASES, k_user
from tests.work_blocks_fixtures import MON, legacy_week

_TEXT_KIND = {
    None: lambda t: t is None,
    "hull": lambda t: t.startswith("Die eingetragene Zeit wurde auf das hinterlegte") and "Zusätzlich" not in t,
    "collapse": lambda t: "vollstaendig ausserhalb" in t,
    "gap": lambda t: t.startswith("Zwischen den Arbeitsblöcken ("),
    "hull+gap": lambda t: t.startswith("Die eingetragene Zeit wurde") and "Zusätzlich werden zwischen den Arbeitsblöcken" in t,
    "in_gap": lambda t: "vollständig zwischen zwei Arbeitsblöcken" in t,
    "clock_in_gap": lambda t: t.startswith("Eingestempelt zwischen zwei Arbeitsblöcken"),
}


@pytest.fixture
def k_setup(db, default_tenant):
    db.add(PublicHoliday(date=EASTER_MONDAY, name="Ostermontag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.add(SystemSetting(key="special_day_dec24_mode", value="half_day", tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


def _entry(case, r):
    return TimeEntry(
        start_time=r.eff_start, end_time=r.eff_end, raw_start_time=r.raw_start,
        raw_end_time=r.raw_end, break_minutes=case.break_minutes,
        uncredited_minutes=r.uncredited_minutes, auto_closed=case.auto_closed,
    )


@pytest.mark.parametrize("case", K_CASES, ids=[c.id for c in K_CASES])
def test_k_table(db, k_setup, case):
    user = k_user(case)
    r = wws.clamp(db, user, case.day, case.start, case.end, 15, credit_override=case.credit_override)
    assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == (
        case.exp_start, case.exp_end, case.exp_raw_start, case.exp_raw_end)
    assert r.uncredited_minutes == case.exp_uncredited
    assert r.grace_minutes == case.exp_grace
    segs = wws.gap_segments(db, user, case.day, case.start, case.end, 15, credit_override=case.credit_override)
    assert sum(segs) == r.uncredited_minutes
    assert wws.not_credited_minutes(_entry(case, r)) == case.exp_not_credited
    text = wws.clamp_warning_text(db, user, case.day, r, for_employee=False)
    assert _TEXT_KIND[case.clamp_text](text), text


def test_result_has_six_fields_and_four_unpack_fails(db, default_tenant):
    r = wws.clamp(db, k_user(K_CASES[0]), MON, time(8), time(18), 15, credit_override=False)
    assert len(r) == 6
    with pytest.raises(ValueError):
        a, b, c, d = r  # noqa: F841 — E31: altes Entpacken scheitert laut


def test_credit_override_is_mandatory(db, default_tenant):
    with pytest.raises(TypeError):
        wws.clamp(db, k_user(K_CASES[0]), MON, time(8), time(18), 15)


def test_start_none_with_end_does_not_crash(db, default_tenant):
    r = wws.clamp(db, k_user(K_CASES[0]), MON, None, time(19), 15, credit_override=False)
    assert r == wws.ClampResult(None, time(18, 15), None, time(19), 0, 15)


def test_preload_parameters_give_same_result(db, default_tenant):
    user = k_user(K_CASES[0])
    plain = wws.clamp(db, user, MON, time(7), time(19), 15, credit_override=False)
    pre = wws.clamp(db, user, MON, time(7), time(19), 15, credit_override=False,
                    wh_changes=[], soll_free_dates=set())
    assert pre == plain
    free = wws.clamp(db, user, MON, time(7), time(19), 15, credit_override=False,
                     wh_changes=[], soll_free_dates={MON})
    assert free == wws.ClampResult(time(7), time(19), None, None, 0, None)


@pytest.mark.parametrize("cid, minutes", [("K7", 720), ("K8", 120), ("K15", 615), ("K20", 660)])
def test_presence_minutes(db, k_setup, cid, minutes):
    case = next(c for c in K_CASES if c.id == cid)
    r = wws.clamp(db, k_user(case), case.day, case.start, case.end, 15, credit_override=False)
    assert wws.presence_minutes(_entry(case, r)) == minutes


def test_hull_text_is_byte_identical_to_1_19():
    r = wws.ClampResult(time(7, 45), time(16, 0), time(7, 37), None, 0, 15)
    assert wws.clamp_warning_text(None, None, None, r, for_employee=True) == (
        "Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt "
        "(Beginn 07:37 → 07:45; Puffer 15 Minuten). Angerechnet wird die gekappte Zeit; "
        "die urspruengliche Eingabe bleibt als Rohstempel gespeichert."
    )


def test_gap_text_and_employee_hint(db, default_tenant):
    user = k_user(K_CASES[0])
    r = wws.clamp(db, user, MON, time(8), time(18), 15, credit_override=False)
    assert wws.clamp_warning_text(db, user, MON, r, for_employee=False) == (
        "Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden "
        "2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."
    )
    with_hint = wws.clamp_warning_text(db, user, MON, r, for_employee=True)
    assert with_hint.endswith(wws.EMPLOYEE_CREDIT_HINT)
    assert wws.clamp_warning(db, user, MON, r, for_employee=False).startswith("WORK_WINDOW_CLAMPED: Zwischen")


def _k(cid):
    return next(c for c in K_CASES if c.id == cid)


def _k_text(db, cid, *, for_employee):
    case = _k(cid)
    user = k_user(case)
    r = wws.clamp(db, user, case.day, case.start, case.end, 15, credit_override=case.credit_override)
    return wws.clamp_warning_text(db, user, case.day, r, for_employee=for_employee)


# Review Task 3: alle vier neuen Texte der Spec 6.2 wörtlich (PR4 zitiert sie in
# der Doku) — nicht nur über ein Fragment wie in ``_TEXT_KIND``.
def test_in_gap_text_k3_exact(db, default_tenant):
    assert _k_text(db, "K3", for_employee=False) == (
        "Die eingetragene Zeit (12:30–14:30) liegt vollständig zwischen zwei Arbeitsblöcken "
        "(Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet werden 0 Stunden. "
        "Die gestempelte Zeit bleibt gespeichert."
    )
    assert _k_text(db, "K3", for_employee=True).endswith(wws.EMPLOYEE_CREDIT_HINT)


def test_hull_and_gap_text_k7_exact(db, default_tenant):
    assert _k_text(db, "K7", for_employee=False) == (
        "Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt "
        "(Beginn 07:00 → 07:45, Ende 19:00 → 18:15; Puffer 15 Minuten). Angerechnet wird "
        "die gekappte Zeit; die urspruengliche Eingabe bleibt als Rohstempel gespeichert."
        " Zusätzlich werden zwischen den Arbeitsblöcken (12:15–14:45) 2:30 h nicht angerechnet."
    )


def test_collapse_text_k8_has_no_employee_hint(db, default_tenant):
    """P21: der Hinweis hängt nur an Lückentexten, nie am Kollaps-Text."""
    text = _k_text(db, "K8", for_employee=True)
    assert text == _k_text(db, "K8", for_employee=False)
    assert "vollstaendig ausserhalb" in text
    assert wws.EMPLOYEE_CREDIT_HINT not in text


def test_clock_in_gap_text(db, default_tenant):
    user = k_user(K_CASES[0])
    r = wws.clamp(db, user, MON, time(13), None, 15, credit_override=False)
    assert wws.clamp_warning_text(db, user, MON, r, for_employee=True) == (
        "Eingestempelt zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) "
        "— angerechnet wird erst ab 14:45."
    )


def test_clamp_applies(db, default_tenant):
    user = k_user(K_CASES[0])
    assert wws.clamp_applies(db, user, MON, credit_override=False) is True
    assert wws.clamp_applies(db, user, MON, credit_override=True) is False
    user.track_hours = False
    assert wws.clamp_applies(db, user, MON, credit_override=False) is False
    user.track_hours = True
    user.work_blocks = None
    assert wws.clamp_applies(db, user, MON, credit_override=False) is False


def test_grace_for_entry_prefers_stored_value(db, default_tenant):
    db.add(SystemSetting(key="work_window_grace_minutes", value="0", tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    stored = TimeEntry(tenant_id=DEFAULT_TENANT_ID, clamp_grace_minutes=15)
    legacy = TimeEntry(tenant_id=DEFAULT_TENANT_ID, clamp_grace_minutes=None)
    assert wws.grace_for_entry(db, stored) == 15
    assert wws.grace_for_entry(db, legacy) == 0


# Review Focus 5: Uhrzeiten mit Sekunden an der Hüllkante — wie 072.
def test_seconds_at_the_hull_edge_behave_like_072(db, default_tenant):
    user = User(username="s", email="s@x.de", password_hash="h", first_name="S", last_name="S",
                role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
                track_hours=True, tenant_id=DEFAULT_TENANT_ID,
                work_blocks=legacy_week(mon=("08:00", "18:00")))
    late = wws.clamp(db, user, MON, time(9), time(18, 15, 30), 15, credit_override=False)
    assert (late.eff_end, late.raw_end) == (time(18, 15), time(18, 15, 30))
    early = wws.clamp(db, user, MON, time(7, 44, 30), time(17), 15, credit_override=False)
    assert (early.eff_start, early.raw_start) == (time(7, 45), time(7, 44, 30))
    edge = wws.clamp(db, user, MON, time(9), time(18, 15), 15, credit_override=False)
    assert edge.raw_end is None
