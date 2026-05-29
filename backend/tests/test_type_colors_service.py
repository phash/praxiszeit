"""Tests für type_colors_service (#157): Admin-konfigurierbare Typ-Farben."""
import json

import pytest

from app.models.system_setting import SystemSetting
from app.services import type_colors_service as svc
from tests.conftest import DEFAULT_TENANT_ID


class TestDefaults:
    def test_returns_defaults_when_unconfigured(self, db, default_tenant):
        colors = svc.get_type_colors(db, DEFAULT_TENANT_ID)
        assert colors == svc.DEFAULT_TYPE_COLORS
        # all expected type keys present
        assert set(colors) == {
            "work", "training", "vacation", "sick", "overtime", "other", "paid_leave"
        }

    def test_all_defaults_are_valid_hex(self):
        for k, v in svc.DEFAULT_TYPE_COLORS.items():
            assert svc._HEX_RE.match(v), f"{k}={v} ist kein #RRGGBB"


class TestSetAndMerge:
    def test_set_overrides_only_given_keys(self, db, default_tenant):
        result = svc.set_type_colors(db, DEFAULT_TENANT_ID, {"vacation": "#123456"})
        assert result["vacation"] == "#123456"
        # untouched keys keep their defaults
        assert result["work"] == svc.DEFAULT_TYPE_COLORS["work"]

    def test_partial_update_preserves_prior_config(self, db, default_tenant):
        svc.set_type_colors(db, DEFAULT_TENANT_ID, {"vacation": "#111111"})
        svc.set_type_colors(db, DEFAULT_TENANT_ID, {"sick": "#222222"})
        colors = svc.get_type_colors(db, DEFAULT_TENANT_ID)
        assert colors["vacation"] == "#111111"  # not lost by the second update
        assert colors["sick"] == "#222222"

    def test_persists_as_json_in_system_setting(self, db, default_tenant):
        svc.set_type_colors(db, DEFAULT_TENANT_ID, {"work": "#ABCDEF"})
        row = db.query(SystemSetting).filter(
            SystemSetting.key == svc.TYPE_COLORS_KEY,
            SystemSetting.tenant_id == DEFAULT_TENANT_ID,
        ).first()
        assert row is not None
        assert json.loads(row.value)["work"] == "#ABCDEF"


class TestValidation:
    def test_rejects_unknown_type_key(self, db, default_tenant):
        with pytest.raises(ValueError):
            svc.set_type_colors(db, DEFAULT_TENANT_ID, {"holiday": "#123456"})

    def test_rejects_invalid_hex(self, db, default_tenant):
        for bad in ["red", "#12345", "#GGGGGG", "123456", "#1234567"]:
            with pytest.raises(ValueError):
                svc.set_type_colors(db, DEFAULT_TENANT_ID, {"vacation": bad})

    def test_corrupt_stored_json_falls_back_to_defaults(self, db, default_tenant):
        db.add(SystemSetting(
            key=svc.TYPE_COLORS_KEY, tenant_id=DEFAULT_TENANT_ID,
            value="{not valid json", description="x",
        ))
        db.commit()
        assert svc.get_type_colors(db, DEFAULT_TENANT_ID) == svc.DEFAULT_TYPE_COLORS
