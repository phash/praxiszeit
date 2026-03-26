"""Tests for review finding fixes."""
import uuid
import pytest
from datetime import date
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from tests.conftest import DEFAULT_TENANT_ID

TENANT_B_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class TestSystemSettingsMultiTenant:
    """C3: system_settings must support same key for different tenants."""

    def test_two_tenants_same_key(self, db, default_tenant):
        """Two tenants can each have their own 'holiday_state' setting."""
        tenant_b = Tenant(id=TENANT_B_ID, name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.commit()

        s1 = SystemSetting(key="test_holiday_state", value="Bayern", tenant_id=DEFAULT_TENANT_ID)
        s2 = SystemSetting(key="test_holiday_state", value="Berlin", tenant_id=TENANT_B_ID)
        db.add(s1)
        db.add(s2)
        db.commit()

        result = db.query(SystemSetting).filter(
            SystemSetting.key == "test_holiday_state"
        ).all()
        assert len(result) == 2
        values = {str(r.tenant_id): r.value for r in result}
        assert values[str(DEFAULT_TENANT_ID)] == "Bayern"
        assert values[str(TENANT_B_ID)] == "Berlin"

        # Cleanup
        db.query(SystemSetting).filter(SystemSetting.key == "test_holiday_state").delete()
        db.query(Tenant).filter(Tenant.id == TENANT_B_ID).delete()
        db.commit()
