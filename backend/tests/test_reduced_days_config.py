"""Verkürzte Tage (Teil B): Modus max_hours und Config/Zustands-API."""

from datetime import date
from decimal import Decimal
import uuid

import pytest

from app.models import ReducedDay, PublicHoliday
from app.services import special_days_service as sds
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_special_days import _set_setting


@pytest.mark.parametrize("raw, ok", [
    ("0.25", Decimal("0.25")), ("12", Decimal("12.00")), ("4,5", None),
    ("0.2", None), ("12.25", None), ("4.3", None), ("abc", None),
])
def test_parse_max_hours(raw, ok):
    if ok is None:
        with pytest.raises(ValueError, match="zwischen 0,25 und 12"):
            sds.parse_max_hours(raw)
    else:
        assert sds.parse_max_hours(raw) == ok


def test_config_includes_reduced_day(db, test_user):
    db.add(ReducedDay(tenant_id=DEFAULT_TENANT_ID, date=date(2026, 2, 16),
                      label="Rosenmontag", max_hours=Decimal("4")))
    db.commit()
    cfg = sds.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    assert cfg[date(2026, 2, 16)] == {
        "mode": "max_hours", "counts_as_vacation": False,
        "max_hours": Decimal("4.00"), "label": "Rosenmontag",
    }
    assert date(2027, 2, 16) not in sds.get_special_day_config(db, DEFAULT_TENANT_ID, 2027)


def test_config_ignores_other_tenant_reduced_day(db, test_user):
    from app.models import Tenant
    other = uuid.uuid4()
    db.add(Tenant(id=other, name="Other", slug="other-" + str(other)[:8]))
    db.commit()
    db.add(ReducedDay(tenant_id=other, date=date(2026, 2, 16),
                      label="X", max_hours=Decimal("4")))
    db.commit()
    assert date(2026, 2, 16) not in sds.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)


def test_setting_max_hours_resolves(db, test_user):
    _set_setting(db, "special_day_dec24_mode", "max_hours")
    _set_setting(db, "special_day_dec24_max_hours", "3.5")
    cfg = sds.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    assert cfg[date(2026, 12, 24)]["max_hours"] == Decimal("3.50")
    assert cfg[date(2026, 12, 24)]["label"] == "Heiligabend"
    assert cfg[date(2026, 12, 31)]["max_hours"] is None
    assert cfg[date(2026, 12, 31)]["label"] == "Silvester"


def test_stray_row_loses_against_setting(db, test_user):
    _set_setting(db, "special_day_dec24_mode", "half_day")
    db.add(ReducedDay(tenant_id=DEFAULT_TENANT_ID, date=date(2026, 12, 24),
                      label="x", max_hours=Decimal("2")))
    db.commit()
    assert sds.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)[date(2026, 12, 24)]["mode"] == "half_day"


def test_mode_max_hours_without_hours_falls_back_to_4(db, test_user):
    _set_setting(db, "special_day_dec24_mode", "max_hours")
    cfg = sds.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    assert cfg[date(2026, 12, 24)]["max_hours"] == Decimal("4")
    s = sds.get_special_day_settings(db, DEFAULT_TENANT_ID)
    assert s["special_day_dec24_max_hours"] == 4.0


@pytest.mark.parametrize("mode, target, expected", [
    ("max_hours", "8", "4"), ("max_hours", "3", "3"), ("max_hours", "0", "0"),
    ("half_day", "8", "4"), ("free", "8", "0"), ("working_day", "8", "8"),
])
def test_special_day_target(mode, target, expected):
    d = date(2026, 12, 24)
    cfg = {d: {"mode": mode, "counts_as_vacation": False,
               "max_hours": Decimal("4") if mode == "max_hours" else None, "label": "x"}}
    assert sds.special_day_target(d, Decimal(target), cfg) == Decimal(expected)
    assert sds.special_day_target(date(2026, 12, 25), Decimal(target), cfg) == Decimal(target)


def test_factor_none_for_max_hours():
    d = date(2026, 12, 24)
    cfg = {d: {"mode": "max_hours", "counts_as_vacation": False,
               "max_hours": Decimal("4"), "label": "x"}}
    assert sds.special_day_target_factor(d, cfg) is None
    assert sds.special_day_mode(d, cfg) == "max_hours"
    assert sds.special_day_mode(date(2026, 1, 1), cfg) is None


def test_reduced_day_label():
    assert sds.reduced_day_label(Decimal("4")) == "verkürzter Tag (max. 4 h)"
    assert sds.reduced_day_label(Decimal("4.50")) == "verkürzter Tag (max. 4,5 h)"
    assert sds.reduced_day_label(Decimal("4.25")) == "verkürzter Tag (max. 4,25 h)"


def test_changed_dates_compares_date_sets():
    before = sds.reduced_day_states([(date(2026, 2, 16), Decimal("4"))])
    after = sds.reduced_day_states([(date(2026, 2, 17), Decimal("4"))])
    assert sds.changed_dates(before, after) == {date(2026, 2, 16), date(2026, 2, 17)}
    assert sds.free_state_changed_dates(before, after) == set()


def test_hours_change_under_working_day_is_no_change():
    b = sds.setting_states({"special_day_dec24_mode": "working_day", "special_day_dec24_max_hours": 3.0,
                            "special_day_dec31_mode": "working_day"}, [2026])
    a = sds.setting_states({"special_day_dec24_mode": "working_day", "special_day_dec24_max_hours": 5.0,
                            "special_day_dec31_mode": "working_day"}, [2026])
    assert sds.changed_dates(b, a) == set()


def test_configs_for_years(db, test_user):
    out = sds.configs_for_years(db, DEFAULT_TENANT_ID, [2026, 2026, 2027])
    assert set(out) == {2026, 2027}


def test_years_affected_ignores_weekend_and_holiday(db, test_user):
    sat = date(2026, 2, 14)
    b = {}
    a = sds.reduced_day_states([(sat, Decimal("4"))])
    assert sds.years_affected_by_change(db, DEFAULT_TENANT_ID, b, a) == []
    mon = date(2026, 2, 16)
    a = sds.reduced_day_states([(mon, Decimal("4"))])
    assert sds.years_affected_by_change(db, DEFAULT_TENANT_ID, b, a) == [2026]
    db.add(PublicHoliday(tenant_id=DEFAULT_TENANT_ID, date=mon, name="H", year=2026))
    db.commit()
    assert sds.years_affected_by_change(db, DEFAULT_TENANT_ID, b, a) == []
